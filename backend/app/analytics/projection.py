"""Team performance projection with an explicit rotation allocator.

Post-trade projection reallocates the 240 regulation minutes per game rather than
naively summing player values: departing minutes are redistributed to arrivals and
incumbents under per-player caps. Net-rating deltas convert to wins through a
historically calibrated linear mapping (fit on ingested team-seasons, not a
hard-coded constant)."""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

TEAM_MINUTES = 240.0
DEFAULT_MAX_MINUTES = 36.0
GAMES = 82.0

# R3-3. Replacement level, derived rather than assumed. The old hardcoded -2.0 sat at the
# **14.1st percentile** of player-season TEI on the ingested history — a rotation player,
# not a replacement one. Measured alternatives on the same data:
#
#     mean TEI outside each team's top 10 by minutes   -1.214   (n = 814)
#     mean TEI outside each team's top 11 by minutes   -1.305   (n = 724)
#     mean TEI, players under 500 total minutes        -1.422   (n = 600)
#
# "Outside the top ten by minutes" is the transparent rule: it is what a team actually
# reaches for when a rotation player is unavailable, and it does not depend on a minutes
# cutoff chosen after the fact.
REPLACEMENT_TEI = -1.214
REPLACEMENT_RULE = "mean TEI of player-seasons outside their team's top 10 by minutes"

# **The one definition of "the rotation"** (R4-4). Three cutoffs existed for what is
# nominally the same idea: `REPLACEMENT_TEI` above was fitted on "outside the top 10",
# `evaluation._fit` took the top **9** to decide what a roster is already strong at, and
# `ROTATION_VIEW_SIZE` charts **12** rows. The third is a display choice and stays separate
# and named as such; the first two are the same basketball claim and must agree, or the
# depth at which a roster is judged strong differs from the depth at which it is judged
# replaceable.
#
# Ten, because that is where `REPLACEMENT_TEI` is already fitted — moving that constant
# would require refitting a calibrated quantity to remove an inconsistency in an
# uncalibrated one.
ROTATION_DEPTH = 10

# R3-2. Change in minutes-weighted team TEI -> change in net rating, fitted
# change-on-change on 60 team transitions (30 teams x 2 transitions):
#
#     d_net = 14.977 * d_teamTEI     R2 0.6236   SE 1.528   t 9.80
#     per-fold slopes 14.716 / 15.276 (within +/-2% of pooled)
#     LOTO OOS RMSE 3.773 vs 5.805 predict-zero (65%)
#
# It is emphatically NOT 1.0, and it is not 5. If TEI were already in additive per-player
# net-rating units the fit would return about 5; it returns 15, which is the quantitative
# statement of how far off the raw index scale is. The fitted value is only valid for the
# exact regressor construction recorded alongside it — see `TEI_REGRESSOR_CONSTRUCTION`.
TEI_TO_NET_RATING = 14.977
TEI_REGRESSOR_CONSTRUCTION = (
    "minutes-weighted mean of the transparent index TEI over a team's player-seasons, "
    "z-scored within season against minutes-weighted moments; served rows are z-scored "
    "against the reference season's moments so train and serve share one scale (C5)"
)


@dataclass
class RotationPlayer:
    player_id: str
    name: str
    tei: float
    baseline_minutes: float  # minutes per game last observed
    availability: float = 1.0
    max_minutes: float = DEFAULT_MAX_MINUTES
    user_minutes: float | None = None  # user-editable override


@dataclass
class RotationResult:
    minutes: dict[str, float]
    team_tei_per_minute: float
    detail: list[dict] = field(default_factory=list)


def allocate_rotation(players: list[RotationPlayer]) -> RotationResult:
    """Distribute 240 minutes proportionally to baseline minutes (a proxy for coach
    trust) with user overrides and per-player caps. Availability discounts expected
    minutes: a 70%-available player contributes 70% of allocated minutes in
    expectation."""
    minutes: dict[str, float] = {}
    remaining = TEAM_MINUTES

    fixed = [p for p in players if p.user_minutes is not None]
    flexible = [p for p in players if p.user_minutes is None]
    for p in fixed:
        allotted = min(max(p.user_minutes or 0.0, 0.0), p.max_minutes)
        minutes[p.player_id] = allotted
        remaining -= allotted
    remaining = max(remaining, 0.0)

    weights = np.array([max(p.baseline_minutes, 2.0) for p in flexible], dtype=float)
    if flexible and weights.sum() > 0:
        # Water-filling (R4-4). The previous six-iteration clip-and-redistribute loop
        # ended each pass ON the redistribution, with no re-clip, so whatever it added
        # back could push a player above his cap and simply stay there: a seven-player
        # trade produced 41.3 minutes against a 36-minute ceiling, and contrived rosters
        # reached 204. For six or fewer flexible players it was a permanent 2-cycle that
        # the iteration bound merely truncated. It was NOT unreachable code.
        #
        # Water-filling instead caps the players who exceed their ceiling, removes their
        # minutes from the budget, and re-shares the remainder among those still under —
        # so it terminates in at most one pass per player, and no allocation can exceed a
        # cap because a capped player is never given more.
        caps = np.array([p.max_minutes for p in flexible], dtype=float)
        alloc = np.zeros(len(flexible), dtype=float)
        free = np.ones(len(flexible), dtype=bool)
        budget = remaining
        while free.any() and budget > 1e-9:
            share = np.zeros(len(flexible), dtype=float)
            share[free] = weights[free] / weights[free].sum() * budget
            newly_capped = free & (share > caps + 1e-12)
            if not newly_capped.any():
                alloc[free] = share[free]
                budget = 0.0
                break
            alloc[newly_capped] = caps[newly_capped]
            budget -= float(caps[newly_capped].sum())
            free &= ~newly_capped
        # If every player is capped and budget remains, the roster cannot field 240
        # minutes. That shortfall is left unallocated on purpose: it flows into the
        # `unfilled` term below and is charged to a replacement-level player, which is
        # the R3-3 behaviour and the honest answer for a gutted roster.
        for p, m in zip(flexible, alloc, strict=False):
            minutes[p.player_id] = float(m)

    # R3-3: normalise by the 240 minutes a team must actually field, NOT by the minutes
    # this roster happened to fill. Dividing by allocated minutes made a gutted roster
    # look fine — the same average taken over fewer minutes — which is the real mechanism
    # behind the roster-gut defect (the `or 1.0` guard the audit named is dead code in
    # the empty-roster path). Minutes a team cannot fill are played by someone, and that
    # someone is a replacement-level player.
    allocated = sum(minutes.values())
    weighted = 0.0
    detail = []
    for p in players:
        m = minutes.get(p.player_id, 0.0)
        effective_tei = p.availability * p.tei + (1 - p.availability) * REPLACEMENT_TEI
        weighted += m / TEAM_MINUTES * effective_tei
        detail.append(
            {
                "player_id": p.player_id,
                "name": p.name,
                "minutes": round(m, 1),
                "tei": round(p.tei, 2),
                "availability": round(p.availability, 3),
            }
        )
    unfilled = max(TEAM_MINUTES - allocated, 0.0)
    weighted += unfilled / TEAM_MINUTES * REPLACEMENT_TEI
    return RotationResult(minutes=minutes, team_tei_per_minute=weighted, detail=detail)


def team_tei_to_net_rating_delta(before: RotationResult, after: RotationResult) -> float:
    """Change in minutes-weighted team TEI, converted to net-rating points (R3-2).

    The conversion used to be the identity, on the reasoning that "TEI is on a per-100
    individual scale". It is not: the index is a weighted z-score on an arbitrary scale,
    and the fitted coefficient is 14.977, not 1.0. Every caller must apply this function
    rather than differencing `team_tei_per_minute` directly, or the point estimate and
    the Monte Carlo disagree by an order of magnitude.
    """
    return TEI_TO_NET_RATING * (after.team_tei_per_minute - before.team_tei_per_minute)


def calibrate_wins_per_net_rating(team_seasons: pd.DataFrame) -> dict:
    """Fit wins = a + b * net_rating on ingested team-seasons (NET_RATING vs actual
    wins). Returns the mapping with fit diagnostics; falls back to the widely
    replicated ~2.7 wins/point with an explicit flag when data is insufficient."""
    # An empty frame has no columns either, so `dropna(subset=...)` raises `KeyError`
    # rather than returning nothing — and `make train` on a database with player stats but
    # no team stats or standings crashed instead of taking the documented fallback below.
    if team_seasons.empty or not {"net_rating", "wins"} <= set(team_seasons.columns):
        return {"slope": 2.7, "intercept": 41.0, "r2": None, "n": 0, "calibrated": False}
    df = team_seasons.dropna(subset=["net_rating", "wins"])
    if len(df) < 30:
        return {"slope": 2.7, "intercept": 41.0, "r2": None, "n": len(df), "calibrated": False}
    x = df["net_rating"].to_numpy(dtype=float)
    y = df["wins"].to_numpy(dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    predictions = slope * x + intercept
    residuals = y - predictions
    ss_res = float((residuals**2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    # The SLOPE's standard error, which is what an interval over the conversion needs.
    # `residual_std` is the spread of team wins about the line — a different quantity,
    # ~55x larger, and using it as the slope's sigma made every band that much too wide.
    slope_se = float(
        np.sqrt(ss_res / max(len(x) - 2, 1) / max(((x - x.mean()) ** 2).sum(), 1e-12))
    )
    # Leave-one-out R2, reported instead of in-sample: the label was the defect here, not
    # the model. Measured 0.9505 LOO against 0.9527 in-sample — the best-calibrated thing
    # in the pipeline, and it should be described accurately.
    loo_residuals = residuals / (
        1 - (1 / len(x) + (x - x.mean()) ** 2 / max(((x - x.mean()) ** 2).sum(), 1e-12))
    )
    loo_r2 = 1 - float((loo_residuals**2).sum()) / ss_tot if ss_tot else None
    return {
        "slope": float(slope),
        "slope_se": slope_se,
        "slope_t": float(slope / slope_se) if slope_se else None,
        "intercept": float(intercept),
        "r2_in_sample": 1 - ss_res / ss_tot if ss_tot else None,
        "r2_loo": loo_r2,
        "residual_std": float(np.std(residuals)),
        "n": len(df),
        "calibrated": True,
    }


def calibrate_tei_to_net_rating(transitions: pd.DataFrame) -> dict:
    """Fit `d_net = b * d_teamTEI` change-on-change, with the diagnostics R3 gates on.

    `transitions` needs `team_id`, `transition`, `d_tei`, `d_net`. Change-on-change
    rather than levels because a team's level carries everything the roster does not —
    coaching, health, schedule — and differencing removes the team fixed effect.
    """
    if transitions.empty or not {"d_tei", "d_net"} <= set(transitions.columns):
        return {"coefficient": TEI_TO_NET_RATING, "calibrated": False, "n": 0}
    df = transitions.dropna(subset=["d_tei", "d_net"])
    if len(df) < 20:
        return {"coefficient": TEI_TO_NET_RATING, "calibrated": False, "n": len(df)}

    x = df["d_tei"].to_numpy(dtype=float)
    y = df["d_net"].to_numpy(dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    residuals = y - (slope * x + intercept)
    ss_res = float((residuals**2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    se = float(np.sqrt(ss_res / max(len(x) - 2, 1) / max(((x - x.mean()) ** 2).sum(), 1e-12)))

    per_fold: dict[str, float] = {}
    loto: dict[str, dict] = {}
    for name in sorted(df["transition"].unique()):
        fold, held = df[df["transition"] != name], df[df["transition"] == name]
        if len(fold) < 10 or held.empty:
            continue
        fold_slope = float(np.polyfit(fold["d_tei"], fold["d_net"], 1)[0])
        per_fold[name] = fold_slope
        rmse = float(np.sqrt(((held["d_net"] - fold_slope * held["d_tei"]) ** 2).mean()))
        zero = float(np.sqrt((held["d_net"] ** 2).mean()))
        loto[name] = {
            "oos_rmse": rmse,
            "predict_zero_rmse": zero,
            "share_of_predict_zero": rmse / zero if zero else None,
        }

    return {
        "coefficient": float(slope),
        "slope_se": se,
        "slope_t": float(slope / se) if se else None,
        "intercept": float(intercept),
        "r2": 1 - ss_res / ss_tot if ss_tot else None,
        "n": len(x),
        "per_fold_slopes": per_fold,
        "leave_one_transition_out": loto,
        "regressor_construction": TEI_REGRESSOR_CONSTRUCTION,
        "calibrated": True,
        "falsification_note": (
            "If TEI were already in additive per-player net-rating units this fit would "
            "return about 5. It returns ~15, which is the quantitative statement of how "
            "far the raw index scale is from net-rating points."
        ),
    }


def net_rating_delta_to_wins(
    delta_net: float, mapping: dict, games_remaining: float = GAMES
) -> float:
    return float(mapping["slope"]) * delta_net * (games_remaining / GAMES)
