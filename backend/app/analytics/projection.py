"""Team performance projection with an explicit rotation allocator.

Two questions, answered differently and deliberately (R5.5).

**What does this roster do with 240 minutes?** The level model: minutes in proportion to
baseline minutes, under per-player caps. Kept because it is the best out-of-sample
predictor available here of what a team actually does.

**What happens to those 240 minutes when the roster changes?** The counterfactual, priced
against the pre-trade allocation rather than re-derived from scratch. An incumbent keeps
the minutes he had, an arrival claims his role on the anchor's own scale, and a
departure's minutes go unfilled — charged to a replacement player, because the player who
would really absorb them cannot be distinguished from one. Re-deriving instead re-shared a
departure's minutes across everyone who stayed, which let a team improve by giving a
rotation player away.

Net-rating deltas convert to wins through a historically calibrated linear mapping (fit on
ingested team-seasons, not a hard-coded constant)."""

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


# R5.5. **The marginal minute is a replacement minute.**
#
# The level model below (proportional to baseline minutes) is kept because it is the best
# out-of-sample predictor of what a roster actually does: handed the season-s roster and
# each player's season-s minutes, it predicts season-(s+1) load at MAE 5.803 over 60
# team-season transitions, against 8.641 for a depth-chart cascade and 8.148 for an
# equal-minutes null. Nothing measured here supports replacing it.
#
# What is replaced is the *counterfactual*. `allocate_rotation` was called independently
# on the before-roster and the after-roster, so a departure's minutes were re-shared
# across everyone who remained, in proportion to baseline minutes. Three measurements say
# that is wrong:
#
#   1. Analytically, removing player j changed team TEI by (w_j/W)*(ebar_-j - e_j), so a
#      removal was scored as an improvement exactly when the player sat below his own
#      team's minutes-weighted mean. That rule predicted the sign on **487 of 487**
#      leave-one-out removals across the 30 rosters, and 191 of the 370 above-replacement
#      players (51.6 %) were measured as addition by subtraction — including 152 rotation
#      players at 15+ minutes.
#   2. On the 59 usable team-season transitions, proportional-to-baseline predicts who
#      absorbs vacated minutes *worse than a permutation of its own weights* (MAE 4.081
#      against a null of 3.437). Every alternative shape beat it.
#   3. The players who really absorb them cannot be told apart. Outside a team's top ten
#      by minutes the spread of served TEI is 1.031 against a mean estimation sd of
#      1.409 — a **signal share of 0.000**. Inside the top ten it is 0.529. Promoting a
#      bench player at his own point estimate is promoting estimation error.
#
# So the freed minutes are charged to a replacement player, which is what `REPLACEMENT_TEI`
# already means ("outside their team's top 10 by minutes") and what `ROTATION_DEPTH`
# already asserts. This also makes the projection exactly monotone: with `anchor` supplied,
# removing a player whose effective TEI is above replacement can never improve the team.
#
# Minutes are only *shed* proportionally, and that direction is kept because the same
# transitions support it: proportional-to-current predicts who gives minutes up at MAE
# 2.813, against 3.375 uniform (t = -7.49) and 4.585 bottom-of-the-chart-first (t = -7.99),
# and it beats its own permutation null (3.517). The two directions are genuinely
# asymmetric and the code now says so.
ABSORPTION_RULE = "freed minutes are replacement minutes; surplus is shed proportionally"


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
    # Minutes this roster could not cover, charged to a replacement player. Published
    # rather than inferred, because it is the whole content of a one-way deal.
    unfilled_minutes: float = 0.0


def _shed_proportionally(
    minutes: dict[str, float], surplus: float, order: list[RotationPlayer]
) -> None:
    """Remove `surplus` minutes, in proportion to what each player currently holds.

    Floored at zero by the same water-filling the cap side uses: a player who runs out
    of minutes stops absorbing the cut and the rest is re-shared among those who have
    minutes left, so the loop terminates in at most one pass per player.
    """
    remaining = surplus
    eligible = {p.player_id for p in order if minutes.get(p.player_id, 0.0) > 1e-12}
    while remaining > 1e-9 and eligible:
        total = sum(minutes[k] for k in eligible)
        if total <= 1e-12:
            break
        if total <= remaining + 1e-12:
            for k in eligible:
                minutes[k] = 0.0
            remaining -= total
            break
        exhausted = set()
        for k in sorted(eligible):
            cut = minutes[k] / total * remaining
            if cut >= minutes[k] - 1e-12:
                exhausted.add(k)
        if not exhausted:
            for k in eligible:
                minutes[k] -= minutes[k] / total * remaining
            remaining = 0.0
            break
        for k in exhausted:
            remaining -= minutes[k]
            minutes[k] = 0.0
        eligible -= exhausted


def allocate_rotation(
    players: list[RotationPlayer], anchor: dict[str, float] | None = None
) -> RotationResult:
    """Distribute 240 minutes across a roster.

    Without `anchor` this is the level model: proportional to baseline minutes (a proxy
    for coach trust) with user overrides and per-player caps.

    With `anchor` — the minutes the same team was allocated *before* the trade — this is
    the counterfactual, and it is a different question. Incumbents keep the minutes they
    already had rather than re-sharing a departure's; a departure therefore leaves
    replacement minutes behind, and an arrival's claim is priced on the anchor's own
    scale so the two sides are comparable. See `ABSORPTION_RULE` above for the three
    measurements behind that choice. Availability is applied downstream, not here: a
    70 %-available player's allocated minutes are his ROLE's minutes, of which he plays
    70 % and a replacement plays the rest.
    """
    minutes: dict[str, float] = {}
    remaining = TEAM_MINUTES

    fixed = [p for p in players if p.user_minutes is not None]
    flexible = [p for p in players if p.user_minutes is None]
    for p in fixed:
        allotted = min(max(p.user_minutes or 0.0, 0.0), p.max_minutes)
        minutes[p.player_id] = allotted
        remaining -= allotted
    remaining = max(remaining, 0.0)

    if anchor is not None:
        return _allocate_against_anchor(players, flexible, minutes, remaining, anchor)

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

    return _score(players, minutes)


def _allocate_against_anchor(
    players: list[RotationPlayer],
    flexible: list[RotationPlayer],
    minutes: dict[str, float],
    remaining: float,
    anchor: dict[str, float],
) -> RotationResult:
    """The post-trade counterfactual, priced against the pre-trade allocation.

    An incumbent keeps the minutes he already had. An arrival claims his established
    role, converted onto the anchor's scale so the two sides are measured the same way:
    the anchor allocated 240 minutes across baseline minutes summing to `W`, so a minute
    of baseline was worth `240/W` allocated minutes, and an arrival's claim is priced at
    that same rate. Without the conversion an arrival's raw minutes-per-game would be
    compared against incumbents' compressed minutes, and every acquisition would look
    like an upgrade purely from the change of units.
    """
    incumbents = [p for p in flexible if p.player_id in anchor]
    arrivals = [p for p in flexible if p.player_id not in anchor]
    if not incumbents:
        # Nothing to anchor to — every modelled player is new. There is no counterfactual
        # to price, so this is the level question again and the level model answers it.
        return allocate_rotation(players)

    # The rate the anchor itself used, recovered FROM the anchor rather than assumed.
    # The anchor allocated `scale * max(baseline, 2)` to each uncapped player, so the
    # ratio of the sums returns `scale` exactly when no cap bound, and a minutes-weighted
    # average of the effective rates when some did.
    held = sum(max(anchor.get(p.player_id, 0.0), 0.0) for p in incumbents)
    claimed = sum(max(p.baseline_minutes, 2.0) for p in incumbents)
    scale = (held / claimed) if claimed > 0 else 1.0

    for p in incumbents:
        minutes[p.player_id] = min(max(anchor.get(p.player_id, 0.0), 0.0), p.max_minutes)
    for p in arrivals:
        minutes[p.player_id] = min(max(p.baseline_minutes, 2.0) * scale, p.max_minutes)

    surplus = sum(minutes.values()) - TEAM_MINUTES
    if surplus > 1e-9:
        # More claimed minutes than a game has. Shed proportionally to what each player
        # holds — the direction the transitions support (MAE 2.813 against 3.375 uniform,
        # t = -7.49, and 4.585 bottom-first, t = -7.99).
        _shed_proportionally(minutes, surplus, flexible)
    # A shortfall is deliberately NOT redistributed. It is the departure's minutes, and
    # `_score` charges them to a replacement player.
    del remaining
    return _score(players, minutes)


def _score(players: list[RotationPlayer], minutes: dict[str, float]) -> RotationResult:
    """Minutes-weighted team TEI, with whatever the roster cannot cover at replacement.

    R3-3: normalise by the 240 minutes a team must actually field, NOT by the minutes
    this roster happened to fill. Dividing by allocated minutes made a gutted roster look
    fine — the same average taken over fewer minutes — which is the real mechanism behind
    the roster-gut defect. Minutes a team cannot fill are played by someone, and that
    someone is a replacement-level player.
    """
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
    return RotationResult(
        minutes=minutes,
        team_tei_per_minute=weighted,
        detail=detail,
        unfilled_minutes=unfilled,
    )


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
    slope_se = float(np.sqrt(ss_res / max(len(x) - 2, 1) / max(((x - x.mean()) ** 2).sum(), 1e-12)))
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
