"""Empirical draft-pick valuation.

A pick is not a number. Four separate things stand between "Portland's 2029 first" and a
value, and this module keeps them separate on purpose:

1. **what the slot is worth** — fitted from draft outcomes, `fit_pick_value_curve`;
2. **where the pick will land** — unknown for a future year, `landing_slot_support`;
3. **whether it conveys at all** — protections and swaps, `PickTerms`;
4. **whether the team even owns it** — `ingestion.draft_picks`, and unverified by default.

Collapsing those into one number is how a protected, swapped 2031 second ends up priced
to four significant figures. Every estimate this module returns carries an interval and a
`precision` field, and the interval is wide because the evidence is thin.

---

## The value curve

The estimand is: **the above-replacement value the player taken at slot k delivers, per
draft class, relative to that class's average pick.**

    player value  =  Σ_seasons  total_minutes · (TEI_season − REPLACEMENT_TEI)     floored at 0
    relative      =  player value ÷ (mean player value of that draft class)

Three properties of that construction matter.

**Absence is a measured zero, not a missing value.** A drafted player who never appears in
the observation window contributed nothing above replacement, and that is exactly what a
bust is worth. Dropping him instead — which is what happens if you average only over
players you can see — is the survivorship error that makes every late pick look useful.

**Within-class normalisation removes the career-stage confound exactly.** The observation
window is three seasons, so a 2016 draftee is seen in years 7–9 and a 2023 draftee in
years 0–2. Those are different quantities. But slot is orthogonal to class by
construction — every class has one player at every slot — so dividing by the class mean
removes the class effect without touching the slot effect. What survives is a *relative*
curve, which is all the `assets` component needs: it prices picks against each other.

**Floored at 0.** A team is not obliged to play a bad player. 88 of 448 drafted players in
the estimation set had negative raw value; a pick cannot be worth less than nothing.

### What the curve is, and what is NOT established about it

Fitted on the 30-team ingested database, classes 2016–2023, seasons 2023-24 … 2025-26:

    rel(k) = 3.3855 · exp(−0.08388 · (k − 1)) + 0.2525        R² 0.7534 on slot means

Leave-one-class-out, ranking the held-out class's 52–58 players by the curve fitted
without them: **mean Spearman 0.4624**, every one of the 8 classes positive (0.369–0.613),
t = 15.36 against zero. A within-class permutation null scores 0.0588.

**It does not significantly beat a two-band round-only rule.** "First-rounders are worth
1.598, second-rounders 0.310" scores 0.4219 on the same protocol; the curve's advantage is
+0.0405, paired t = 1.33, **p = 0.22**, 6 of 8 classes. A four-band model scores 0.4808,
which is if anything better and also indistinguishable. The smooth curve is used because it
is not worse than any alternative and because the thing it adds *is* independently
established: **within the first round alone**, the curve orders the held-out class at mean
Spearman **0.3277, 8 of 8 classes positive, t = 4.67, p = 0.0023**. First-round picks are
the currency of trades, and the slot gradient inside that round is real.

**Bootstrap over draft classes says point values are not justified.** Resampling the 8
classes 2,000 times, the 90 % interval at slot 1 is [2.98, 5.64] on a fit of 3.64 — 73 % of
the value. At slot 60 it is 150 %. Nothing here returns a bare number.

**A single pick's outcome is far more skewed than its mean.** Measured on the same set:

    slots  1–5    mean 3.249   median 3.278   38 % below half the mean   12 % exactly zero
    slots  6–14   mean 1.805   median 1.280                              31 % exactly zero
    slots 15–30   mean 0.965   median **0.150**                          38 % exactly zero
    slots 31–60   mean 0.310   median **0.000**                          66 % exactly zero

The median mid-first-round pick returns almost nothing. A mean is the right input to an
expected-value calculation and the wrong thing to show a decision-maker on its own, so the
band is always published beside it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .projection import REPLACEMENT_TEI

# Fitted on the ingested 30-team database; refit by `fit_pick_value_curve` at train time
# and registered as the `pick_value_curve` model version. These constants are the
# fallback when no fit is registered, and the values the tests pin.
PICK_CURVE_A = 3.3855
PICK_CURVE_B = 0.08388
PICK_CURVE_C = 0.2525

#: Bootstrap 90 % band as a multiple of the fitted value, by slot, from resampling the 8
#: estimation classes 2,000 times. Interpolated between the anchors below. The band is
#: wide at slot 1 (one player per class, and that player is sometimes a franchise
#: cornerstone), narrows through the mid-lottery where the classes agree, and widens again
#: in the second round where most picks are worth nothing at all.
_BAND_ANCHORS: list[tuple[int, float, float]] = [
    # (slot, low multiple, high multiple)
    (1, 0.818, 1.549),
    (5, 0.878, 1.070),
    (10, 0.622, 1.057),
    (15, 0.566, 1.138),
    (20, 0.661, 1.217),
    (30, 0.866, 1.264),
    (40, 0.899, 1.433),
    (50, 0.701, 1.770),
    (60, 0.472, 1.971),
]

#: Draft classes the curve is estimated on. Chosen as the classes whose **first round** is
#: completely represented in the player table — 8 classes x 30 slots, 240 of 240 cells
#: present. The second round has 32 of 240 cells absent, which are slots whose selection
#: never played an NBA minute *or* was never made; the two are indistinguishable here, so
#: those cells are excluded and the exclusion is reported rather than imputed as zero.
DEFAULT_ESTIMATION_CLASSES = tuple(range(2016, 2024))

#: The reference asset the `assets` component is anchored on: a mid-first-round pick. Its
#: relative value is ~1.30, and it is worth the 8 composite points a pick has always been
#: worth, so no scale constant changes — only the relative pricing of everything else.
REFERENCE_SLOT = 15

#: The NBA lottery draws the top four selections, so a lottery team can fall **at most
#: four** places below its record-based slot, and any lottery team can rise to first. That
#: is a structural fact about the draw, not an estimate of its odds. The odds table itself
#: is deliberately NOT reproduced here: it would be a published table entered from memory,
#: and this module has no source for it. The consequence is that a lottery pick's landing
#: slot is given as a **support**, not a distribution.
LOTTERY_SLOTS = 14
LOTTERY_MAX_FALL = 4

#: The sd of a uniform draw over 30 ranks — the no-information ceiling. Slot uncertainty
#: is never allowed to exceed it, because "we know nothing" is the worst case and a
#: random walk extrapolated far enough would claim to know less than nothing.
UNINFORMED_RANK_SD = float(np.std(np.arange(1, 31)))

#: Fallback one-year rank drift, used only when no fit is registered. It is the
#: no-information ceiling **on purpose**: an unfitted drift is not a small drift.
#:
#: The fitted value on the ingested standings is **8.53** rank places over 60 team
#: transitions — against a ceiling of 8.66. Year-to-year rank correlation is 0.602 and
#: 0.509 across the two available transitions. A team's finish one year out is therefore
#: only just more predictable than a coin flip on this data, which is the single most
#: important reason nothing in this module returns a precise value for a future pick.
RANK_CHANGE_SD_ONE_YEAR = UNINFORMED_RANK_SD


def relative_pick_value(
    slot: float, curve: dict[str, float] | None = None
) -> float:
    """Fitted relative value of the selection at `slot` (1..60), class-mean = 1.0."""
    c = curve or {"a": PICK_CURVE_A, "b": PICK_CURVE_B, "c": PICK_CURVE_C}
    return float(c["a"] * math.exp(-c["b"] * (max(slot, 1.0) - 1.0)) + c["c"])


def value_band(slot: float, curve: dict[str, float] | None = None) -> tuple[float, float]:
    """Bootstrap 90 % band around the fitted value at `slot`.

    Interpolated between measured anchors rather than modelled, because the band's shape
    is not smooth: it is driven by which classes happen to contain an outlier at that
    slot, and a fitted band would imply a regularity the resampling does not show.
    """
    point = relative_pick_value(slot, curve)
    slots = [a[0] for a in _BAND_ANCHORS]
    low = float(np.interp(slot, slots, [a[1] for a in _BAND_ANCHORS]))
    high = float(np.interp(slot, slots, [a[2] for a in _BAND_ANCHORS]))
    return point * low, point * high


def expected_rank_from_win_pct(win_pct: float) -> float:
    """League rank (1 = best record) implied by a win percentage.

    A linear map over the observed spread of NBA win percentages, which is what a rank is:
    0.850 -> 1st, 0.150 -> 30th. Deliberately crude — the quantity it feeds is a support,
    not a point estimate.
    """
    share = (0.850 - win_pct) / (0.850 - 0.150)
    return 1.0 + 29.0 * min(max(share, 0.0), 1.0)


def rank_uncertainty(years_out: int, one_year_sd: float = RANK_CHANGE_SD_ONE_YEAR) -> float:
    """How far a team's rank can drift by a draft `years_out` seasons from now.

    Only one-year transitions are observable in three seasons of standings, so multi-year
    drift is extrapolated as a random walk, `sd·sqrt(n)` — **an assumption, stated as
    one** — and capped at the no-information sd of a uniform rank. Past about four years
    out the cap binds, which is the honest answer: nobody knows where a 2032 pick lands.
    """
    if years_out <= 0:
        return 0.0
    return float(min(one_year_sd * math.sqrt(years_out), UNINFORMED_RANK_SD))


def landing_slot_support(
    win_pct: float | None,
    years_out: int,
    round_number: int = 1,
    one_year_sd: float = RANK_CHANGE_SD_ONE_YEAR,
) -> dict[str, Any]:
    """Plausible range of slots a team's own pick can land in, with its central estimate.

    Returns a **support**, not a distribution. Two things are unmodelled and said so: the
    lottery's odds (only its structure is used — a team can fall at most four places, and
    any lottery team can rise to first), and any information about a future roster beyond
    the current record.
    """
    round_offset = 30 * (round_number - 1)
    if win_pct is None:
        return {
            "central_slot": None,
            "min_slot": 1 + round_offset,
            "max_slot": 30 + round_offset,
            "basis": "no standings for this team; the whole round is the support",
            "rank_sd": UNINFORMED_RANK_SD,
            "lottery_exposed": round_number == 1,
        }
    rank = expected_rank_from_win_pct(win_pct)
    # Draft order is reverse standings: the worst record picks first.
    central = 31.0 - rank
    sd = rank_uncertainty(years_out, one_year_sd)
    low = central - 1.645 * sd
    high = central + 1.645 * sd
    lottery_exposed = round_number == 1 and low <= LOTTERY_SLOTS
    if lottery_exposed:
        # Structural, not probabilistic: the four drawn selections can push this pick down
        # at most four places, and the draw can lift any lottery team to first.
        low = 1.0
        high = min(high + LOTTERY_MAX_FALL, 30.0)
    return {
        "central_slot": round(central + round_offset, 1),
        "min_slot": int(max(1, math.floor(low)) + round_offset),
        "max_slot": int(min(30, math.ceil(high)) + round_offset),
        "basis": (
            f"reverse standings from a {win_pct:.3f} win percentage, "
            f"±1.645 sd of {sd:.2f} rank places at {years_out} year(s) out"
            + (
                "; widened to the whole lottery range because the pick is lottery-exposed "
                "and this module does not model the draw's odds"
                if lottery_exposed
                else ""
            )
        ),
        "rank_sd": sd,
        "lottery_exposed": lottery_exposed,
    }


@dataclass(frozen=True)
class PickTerms:
    """Everything about a pick that is not its slot."""

    draft_year: int
    round_number: int
    #: The team whose on-court record determines the slot, when it is known.
    original_team_win_pct: float | None = None
    #: Raw protection text as recorded by the source, e.g. "protected for selections 1-4".
    protections: str | None = None
    #: True when the pick is part of a swap, or its conveyance depends on another event.
    is_conditional: bool = False
    #: False unless an ownership source has been reconciled for this pick.
    ownership_verified: bool = False
    unresolved_reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PickValue:
    """A pick's value in class-mean units, always as an interval."""

    low: float
    point: float | None
    high: float
    precision: str  # "interval" | "range" | "unknown"
    slot_support: dict[str, Any]
    basis: str
    caveats: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "low": round(self.low, 4),
            "point": round(self.point, 4) if self.point is not None else None,
            "high": round(self.high, 4),
            "precision": self.precision,
            "slot_support": self.slot_support,
            "basis": self.basis,
            "caveats": list(self.caveats),
        }


def protection_range(protections: str | None) -> tuple[int, int] | None:
    """Parse "protected for selections 1-4" into (1, 4). None when there is no such
    phrase — including when the text says something this cannot read, which is treated as
    unparsed rather than as unprotected."""
    if not protections:
        return None
    import re

    match = re.search(r"selections?\s+(\d+)\s*[-–]\s*(\d+)", protections, re.IGNORECASE)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = re.search(r"top[- ](\d+)", protections, re.IGNORECASE)
    if match:
        return 1, int(match.group(1))
    return None


def pick_value(
    terms: PickTerms,
    current_year: int,
    curve: dict[str, float] | None = None,
) -> PickValue:
    """Value a pick, refusing precision the evidence does not support.

    Three precision levels, and which one you get is a statement about the evidence:

    - `interval` — an unconditional pick with verified ownership. The band is the
      bootstrap band at the central slot, widened across the landing-slot support.
    - `range` — the pick is protected, swapped or otherwise conditional. The bounds span
      the outcomes; there is **no point estimate**, because averaging over conditions this
      module cannot price is how a conditional pick acquires a false decimal.
    - `unknown` — ownership is unverified. Bounds still describe the asset, the point is
      withheld, and the caveat says why.
    """
    years_out = max(terms.draft_year - current_year, 0)
    support = landing_slot_support(
        terms.original_team_win_pct, years_out, terms.round_number
    )
    caveats: list[str] = []

    best_slot = support["min_slot"]
    worst_slot = support["max_slot"]
    low = value_band(worst_slot, curve)[0]
    high = value_band(best_slot, curve)[1]

    protection = protection_range(terms.protections)
    conditional = terms.is_conditional or protection is not None or (
        terms.protections is not None and protection is None
    )

    if protection is not None:
        caveats.append(
            f"protected for selections {protection[0]}-{protection[1]}: the pick does not "
            "convey at all if it lands inside that range, so the low bound is zero"
        )
        low = 0.0
    if terms.protections is not None and protection is None:
        caveats.append(
            "the protection text could not be parsed into a selection range, so the pick "
            "is treated as conditional and no point estimate is offered: "
            f"{terms.protections!r}"
        )
    if terms.is_conditional:
        caveats.append(
            "this pick is part of a swap or its conveyance depends on another event; "
            "its value depends on a second team's finish, which this module does not model"
        )
    if years_out >= 4:
        caveats.append(
            f"{years_out} years out — the landing-slot support is at the no-information "
            "ceiling, so the interval spans essentially the whole round"
        )
    for reason in terms.unresolved_reasons:
        caveats.append(reason)

    if not terms.ownership_verified:
        caveats.insert(
            0,
            "ownership is not verified against a reconciled source; this is the value of "
            "the asset described, not a claim that this team holds it",
        )
        precision = "unknown"
        point = None
    elif conditional:
        precision = "range"
        point = None
    else:
        precision = "interval"
        point = relative_pick_value(support["central_slot"] or REFERENCE_SLOT, curve)

    return PickValue(
        low=low,
        point=point,
        high=high,
        precision=precision,
        slot_support=support,
        basis=(
            "empirical value curve fitted on draft classes "
            f"{DEFAULT_ESTIMATION_CLASSES[0]}-{DEFAULT_ESTIMATION_CLASSES[-1]}, "
            "in class-mean units; interval is the class bootstrap band across the "
            "landing-slot support"
        ),
        caveats=tuple(caveats),
    )


# ------------------------------------------------------------------------ fitting


def _exp_decay(k: np.ndarray, a: float, b: float, c: float) -> np.ndarray:
    return a * np.exp(-b * (k - 1.0)) + c


def build_draft_outcomes(
    season_frame: pd.DataFrame,
    tei_by_player_season: pd.Series,
    drafted: pd.DataFrame,
    classes: tuple[int, ...] = DEFAULT_ESTIMATION_CLASSES,
) -> pd.DataFrame:
    """One row per drafted player in `classes`, with the value the window observed.

    `drafted` needs `player_id`, `draft_year`, `draft_number`. A drafted player with no
    row in the window frame is kept with value 0 — that is the survivorship correction,
    and it is the whole reason the curve does not flatten out in the second round.
    """
    frame = season_frame.copy()
    frame["tei"] = tei_by_player_season.to_numpy()
    frame["value"] = frame["total_minutes"].astype(float) * (
        frame["tei"] - REPLACEMENT_TEI
    )
    per_player = frame.groupby("player_id")["value"].sum()

    rows = []
    for row in drafted.itertuples():
        if row.draft_year not in classes or not row.draft_number:
            continue
        raw = float(per_player.get(row.player_id, 0.0))
        rows.append(
            {
                "player_id": row.player_id,
                "draft_year": int(row.draft_year),
                "slot": int(row.draft_number),
                "value_raw": raw,
                "value": max(raw, 0.0),
                "observed": row.player_id in per_player.index,
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    class_mean = out.groupby("draft_year")["value"].transform("mean")
    out["rel"] = out["value"] / class_mean.replace(0.0, np.nan)
    return out.dropna(subset=["rel"])


def _fit_curve(outcomes: pd.DataFrame) -> tuple[dict[str, float], float] | None:
    from scipy import optimize

    by_slot = outcomes.groupby("slot")["rel"].mean()
    if len(by_slot) < 10:
        return None
    k = by_slot.index.to_numpy(dtype=float)
    v = by_slot.to_numpy(dtype=float)
    try:
        popt, _ = optimize.curve_fit(
            _exp_decay, k, v, p0=[float(v.max()), 0.05, 0.05], maxfev=40000,
            bounds=([0.0, 1e-4, 0.0], [50.0, 1.0, 5.0]),
        )
    except Exception:  # noqa: BLE001 — a failed fit is reported, never silently defaulted
        return None
    pred = _exp_decay(k, *popt)
    ss_res = float(((v - pred) ** 2).sum())
    ss_tot = float(((v - v.mean()) ** 2).sum())
    curve = {"a": float(popt[0]), "b": float(popt[1]), "c": float(popt[2])}
    return curve, (1 - ss_res / ss_tot if ss_tot else 0.0)


def fit_pick_value_curve(outcomes: pd.DataFrame) -> dict[str, Any]:
    """Fit the curve and run the diagnostics R5 gates on.

    Every diagnostic here is reported whether it passes or not, including the one that
    fails: the curve does **not** significantly beat a round-only rule.
    """
    from scipy import stats

    if outcomes.empty:
        return {"calibrated": False, "reason": "no drafted players in the estimation set"}
    fitted = _fit_curve(outcomes)
    if fitted is None:
        return {"calibrated": False, "reason": "curve fit did not converge"}
    curve, r2 = fitted
    classes = sorted(outcomes["draft_year"].unique())

    loco: list[float] = []
    round_only: list[float] = []
    first_round_only: list[float] = []
    rng = np.random.default_rng(20260812)
    null: list[float] = []
    for held in classes:
        train = outcomes[outcomes["draft_year"] != held]
        test = outcomes[outcomes["draft_year"] == held]
        sub = _fit_curve(train)
        if sub is None or len(test) < 5:
            continue
        predicted = _exp_decay(test["slot"].to_numpy(dtype=float), **sub[0])
        loco.append(float(stats.spearmanr(predicted, test["rel"]).statistic))
        null.append(
            float(stats.spearmanr(predicted, rng.permutation(test["rel"].to_numpy())).statistic)
        )
        first = train[train["slot"] <= 30]["rel"].mean()
        second = train[train["slot"] > 30]["rel"].mean()
        band = np.where(test["slot"].to_numpy() <= 30, first, second)
        round_only.append(float(stats.spearmanr(band, test["rel"]).statistic))
        r1 = test[test["slot"] <= 30]
        if len(r1) >= 5:
            first_round_only.append(
                float(
                    stats.spearmanr(
                        _exp_decay(r1["slot"].to_numpy(dtype=float), **sub[0]), r1["rel"]
                    ).statistic
                )
            )

    def _t(values: list[float]) -> dict[str, float | None]:
        if len(values) < 3:
            return {"mean": None, "t": None, "p": None, "n": len(values)}
        result = stats.ttest_1samp(values, 0.0)
        return {
            "mean": float(np.mean(values)),
            "t": float(result.statistic),
            "p": float(result.pvalue),
            "n": len(values),
        }

    paired: dict[str, float | None] = {"mean_gain": None, "t": None, "p": None}
    if len(loco) == len(round_only) >= 3:
        rel = stats.ttest_rel(loco, round_only)
        paired = {
            "mean_gain": float(np.mean(loco) - np.mean(round_only)),
            "t": float(rel.statistic),
            "p": float(rel.pvalue),
        }

    return {
        "calibrated": True,
        "curve": curve,
        "r2_slot_means": r2,
        "classes": [int(c) for c in classes],
        "n_players": int(len(outcomes)),
        "n_observed": int(outcomes["observed"].sum()),
        "leave_one_class_out": _t(loco),
        "permutation_null": _t(null),
        "round_only_baseline": _t(round_only),
        "curve_minus_round_only": paired,
        "first_round_gradient": _t(first_round_only),
        "estimand": (
            "above-replacement window value per drafted player, floored at zero, "
            "normalised by the mean of that player's draft class"
        ),
        "not_established": (
            "The curve does not significantly beat a two-band round-only rule "
            "(see curve_minus_round_only). What is established is the slot gradient "
            "WITHIN the first round (see first_round_gradient). Point values are never "
            "reported without the class-bootstrap band."
        ),
    }


def fit_rank_persistence(standings: pd.DataFrame) -> dict[str, Any]:
    """sd of a team's one-year change in league win-percentage rank.

    `standings` needs `team_id`, `season`, `win_pct`. Returns the fallback with
    `calibrated: False` when there are fewer than two seasons to difference.
    """
    if standings.empty or standings["season"].nunique() < 2:
        return {"calibrated": False, "sd": RANK_CHANGE_SD_ONE_YEAR, "n": 0}
    ranked = standings.copy()
    ranked["rank"] = ranked.groupby("season")["win_pct"].rank(ascending=False, method="min")
    seasons = sorted(ranked["season"].unique())
    changes: list[float] = []
    for a, b in zip(seasons[:-1], seasons[1:], strict=False):
        left = ranked[ranked["season"] == a].set_index("team_id")["rank"]
        right = ranked[ranked["season"] == b].set_index("team_id")["rank"]
        joined = left.to_frame("a").join(right.to_frame("b"), how="inner")
        changes.extend((joined["b"] - joined["a"]).tolist())
    if len(changes) < 10:
        return {"calibrated": False, "sd": RANK_CHANGE_SD_ONE_YEAR, "n": len(changes)}
    return {
        "calibrated": True,
        "sd": float(np.std(changes)),
        "n": len(changes),
        "transitions": len(seasons) - 1,
        "note": (
            "one-year rank drift, measured. Multi-year drift is extrapolated as a random "
            "walk (sd·sqrt(n)) and capped at the uniform-rank sd — an assumption, not a "
            "measurement, because three seasons of standings contain no multi-year "
            "transition to fit."
        ),
    }
