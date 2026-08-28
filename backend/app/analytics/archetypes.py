"""Player roles from a deterministic, size-first rule chain.

**K-means is retired (R4-3).** It was not merely imprecise, it was unstable and
degenerate, measured on the real 632-player window frame:

- Only **5 of its 10 label branches were ever reached**. `defensive big`, `stretch big`,
  `movement shooter`, `point-of-attack guard` and `role player` never fired at all.
- **217 of 632 rows (34.3 %)** carried a numeric suffix — `primary creator (2)` — because
  several clusters landed on the same label and were disambiguated by counter rather than
  by meaning.
- Silhouette **0.154**: no separated structure exists in this feature space, so no choice
  of k finds one. The plan is right that sweeping k is pointless.
- The decisive defect, which nothing previously measured: **dropping a random 10 % of
  players rewrote 65.7 % of the surviving players' labels** (200 seeds, ARI 0.647). A
  label that changes two times in three when the population moves slightly is not a
  property of the player.
- It silently **fabricated size for 49 players (7.75 %)** whose `height_inches` is NULL,
  by filling the league median before clustering.

The replacement is a total, deterministic function of one player's row plus league
percentile cut points. On the identical resampling protocol it moves **1.78 %** of labels
(ARI 0.968), every one of its 14 roles fires, the largest holds 12.2 % and the smallest
3.5 %, the Herfindahl index is 0.080 against k-means' 0.238, and repeated runs are
byte-identical across process invocations and BLAS thread counts.

**Size gates first, deliberately.** A creation-first chain — the intuitive ordering, and
effectively what k-means used — was measured to label Wembanyama a secondary creator.
Height constrains which roles are available before any skill does.

Nothing here is fitted and nothing is random, so there is no silhouette to report and no
seed to fix. Thresholds are league percentiles recomputed from the scored frame, so the
chain stays calibrated if the distribution shifts rather than encoding today's league in
magic numbers.
"""

import hashlib
import inspect
from functools import lru_cache

import numpy as np
import pandas as pd

from app.domain.archetypes import (
    REAL_ROLES,  # noqa: F401  re-exported: tests/unit/test_roles.py imports it from here
    ROLE_ID,
    ROLE_ORDER,
    UNCLASSIFIED_SIZE,
    UNCLASSIFIED_STATS,
)
from app.domain.needs import UNADDRESSABLE_NEEDS as _DOMAIN_UNADDRESSABLE_NEEDS
from app.domain.skills import SKILL_KEYS

from .features import MODEL_FEATURES

ROLE_FEATURES = [
    "height_inches",
    "USG_PCT",
    "AST_PCT",
    "fg3a_rate",
    "stl_per_min",
    "blk_per_min",
    "OREB_PCT",
]
SIZE_FEATURE = "height_inches"
DISCRIMINANTS = ["USG_PCT", "AST_PCT", "fg3a_rate", "stl_per_min", "blk_per_min", "OREB_PCT"]
MAX_MISSING_DISCRIMINANTS = 2
PERCENTILES = (30, 55, 60, 65, 70, 75, 80, 90)

# The role vocabulary is owned by `app.domain.archetypes` and re-exported here, so every
# existing consumer keeps its import and every persisted `role_id` keeps its meaning. The
# map is still frozen and append-only for exactly the same reason; it simply lives one
# layer down now, beside the product-language definition of each label.


def league_thresholds(weighted: pd.DataFrame) -> dict[str, dict[int, float]]:
    """League percentile cut points, computed from the scored frame itself.

    Unweighted over the window frame on purpose: each row is already minutes- and
    recency-weighted per player, so weighting again would over-represent starters and
    make the cuts a function of playing time rather than of the league.

    A column with fewer than 30 observations is omitted entirely, and every branch that
    reads it then evaluates False — so a thin column narrows the chain visibly instead of
    passing silently on a cut derived from a handful of players.
    """
    thresholds: dict[str, dict[int, float]] = {}
    for col in ROLE_FEATURES:
        series = pd.to_numeric(weighted.get(col), errors="coerce").dropna()
        if len(series) < 30:
            continue
        arr = np.sort(series.to_numpy(dtype=float))
        thresholds[col] = {p: float(np.percentile(arr, p, method="linear")) for p in PERCENTILES}
    return thresholds


def assign_role(row: pd.Series, thresholds: dict[str, dict[int, float]]) -> str:
    """Size-first rule chain. Total, deterministic, no randomness, no fitting.

    Within each size tier the branches run from the rarest and most lineup-constraining
    trait to the most common, so a player who satisfies several is named by the one that
    most constrains how a coach can use him. That ordering was committed before any
    named-player check was run.
    """

    def value(col: str) -> float | None:
        x = pd.to_numeric(row.get(col), errors="coerce")
        return None if pd.isna(x) else float(x)

    def ge(col: str, pct: int) -> bool:
        # True only if the value exists AND the league cut exists AND value >= cut.
        # Ties are inclusive, so a player sitting exactly on a cut takes the earlier
        # branch and every player with an identical value takes an identical branch.
        x = value(col)
        return x is not None and col in thresholds and x >= thresholds[col][pct]

    height = value(SIZE_FEATURE)
    if height is None or SIZE_FEATURE not in thresholds:
        # Missing size does NOT fall through into a real role. k-means filled the league
        # median and produced a confident label for 49 players whose height nobody
        # recorded. This gets a visible label instead, so the gap is counted and fixable
        # rather than absorbed.
        return UNCLASSIFIED_SIZE
    if sum(value(c) is None for c in DISCRIMINANTS) > MAX_MISSING_DISCRIMINANTS:
        return UNCLASSIFIED_STATS

    if height >= thresholds[SIZE_FEATURE][75]:  # ---------------------------- BIG
        if ge("fg3a_rate", 60):
            return "stretch big"
        if ge("blk_per_min", 90):
            return "rim-protecting big"
        if ge("AST_PCT", 60):
            return "playmaking big"
        if ge("OREB_PCT", 80):
            return "glass-cleaning big"
        return "finishing big"

    if height >= thresholds[SIZE_FEATURE][30]:  # --------------------------- WING
        if ge("USG_PCT", 75) and ge("AST_PCT", 60):
            return "primary wing creator"
        if ge("fg3a_rate", 60) and ge("stl_per_min", 65):
            return "3&D wing"
        if ge("fg3a_rate", 65):
            return "movement shooter"
        if ge("USG_PCT", 55):
            return "slashing wing"
        return "connector wing"

    if ge("AST_PCT", 80):  # ----------------------------------------------- GUARD
        return "lead guard"
    if ge("USG_PCT", 65):
        return "scoring guard"
    if ge("stl_per_min", 70):
        return "point-of-attack guard"
    return "off-ball guard"


def fit_archetypes(weighted: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Assign a role to every scored player. Returns (assignments, metadata).

    Keeps the name `fit_archetypes` because `train.py` and the API speak of archetypes,
    but nothing is fitted any more: the same frame always produces the same labels.
    """
    if weighted.empty or "player_id" not in weighted.columns:
        return pd.DataFrame(), {"note": "no scored players to label"}

    thresholds = league_thresholds(weighted)
    labels = [assign_role(row, thresholds) for _, row in weighted.iterrows()]
    out = (
        pd.DataFrame(
            {
                "player_id": weighted["player_id"].to_numpy(),
                "role_id": [ROLE_ID[label] for label in labels],
                "label": labels,
            }
        )
        .sort_values("player_id", kind="mergesort")
        .reset_index(drop=True)
    )

    counts = out["label"].value_counts()
    n = len(out)
    meta = {
        "method": "size-first deterministic rule chain",
        "chain_version": "v1",
        "n_players": int(n),
        "roles": ROLE_ORDER,
        "features": ROLE_FEATURES,
        "thresholds": {
            c: {str(p): round(v, 6) for p, v in d.items()} for c, d in sorted(thresholds.items())
        },
        "distribution": {label: int(counts.get(label, 0)) for label in ROLE_ORDER},
        "herfindahl": round(float(((counts / n) ** 2).sum()), 6) if n else None,
        "max_share": round(float(counts.max() / n), 6) if n else None,
        "unclassified": {
            UNCLASSIFIED_SIZE: int(counts.get(UNCLASSIFIED_SIZE, 0)),
            UNCLASSIFIED_STATS: int(counts.get(UNCLASSIFIED_STATS, 0)),
        },
    }
    return out, meta


# Skill dimensions used by roster-fit; derived from the same feature space so that team
# needs and player skills are directly comparable. The list is owned by
# `app.domain.skills` — where each dimension also carries its definition, its method and
# its limitations — and re-exported here.
#
# `skill_schema_fingerprint()` below hashes the CONTENTS of this list, not its address, so
# moving it changes no cache identity. Reordering or renaming still would.

# R5.5. **What a replacement player looks like in skill space**, measured on the same
# population `REPLACEMENT_TEI` is fitted on: rostered players outside their team's top ten
# by minutes (n = 187 across 30 teams, against 300 inside).
#
#     skill                inside   OUTSIDE   t vs 0.5
#     scoring               0.632    0.391      -5.99
#     creation              0.568    0.420      -3.97
#     shooting_volume       0.540    0.444      -2.66
#     turnover_avoidance    0.520    0.446      -2.46
#     size                  0.453    0.468      -1.48
#     shooting_accuracy     0.552    0.482      -0.93
#     rim_protection        0.500    0.516      +0.71
#     team_defense          0.505    0.522      +1.01
#     rebounding            0.497    0.528      +1.36
#
# **The shape is the finding, not the level.** The mean across skills is 0.469, only 0.031
# below the flat 0.5 that R1 removed from `fit_score` as a fabricated median player — but
# the spread across skills is 0.136, four times that gap. What separates a bench player is
# that he cannot score or create; he rebounds and protects the rim at roughly a league
# median rate, and those three skills are not distinguishable from 0.5 at all. A single
# scalar, at 0.5 or at 0.469, would erase exactly the part that carries information.
#
# Four of the nine are not separated from 0.5 on their own, and they are used at their
# measured values anyway: 0.5 is not the better-supported alternative for them, it is
# simply a different unmeasured constant. Leave-one-team-out moves no skill mean by more
# than 0.0092.
REPLACEMENT_SKILLS: dict[str, float] = {
    "shooting_volume": 0.4436,
    "shooting_accuracy": 0.4821,
    "creation": 0.4201,
    "turnover_avoidance": 0.4462,
    "team_defense": 0.5221,
    "rim_protection": 0.5164,
    "rebounding": 0.5278,
    "size": 0.4683,
    "scoring": 0.3914,
}
REPLACEMENT_SKILL_RULE = (
    "mean skill percentile of rostered players outside their team's top 10 by minutes "
    "(n = 187), the same population REPLACEMENT_TEI is fitted on"
)

# Needs the product measures on the team side but **declines to claim any player skill
# addresses**, with the reason shown wherever the need is. This is not a TODO list; it is
# the honest half of R4-2.
#
# `point_of_attack_defense` was built and then withdrawn. Its pre-registered class check —
# high-usage, high-assist, sub-6'8" players with real minutes, the population the tool
# used to overrate — came out at mean 0.630 with 75 % above the median, WORSE than the
# steals proxy it was meant to replace (0.611, 70 %). A steals-led composite cannot help
# but rate ball-dominant guards highly, because gambling for steals is what shows up in a
# box score and staying in front of a ball handler is not.
#
# The anti-overfitting rule (A''') says the response to a failed check is not to tune the
# weights until it passes. So the claim is withdrawn instead: no player skill asserts it
# improves on-ball defence, because nothing in this repository measures on-ball defence.
# That needs the matchup and tracking data deferred to R6. The team-side need is still
# computed and still shown — a team that cannot contain a ball handler should be told so —
# it simply no longer has a player-side answer attached to it.
# Re-exported from `app.domain.needs`, which holds the reason text beside the need's own
# definition. The claim was built and then withdrawn; the reason travels with it.
UNADDRESSABLE_NEEDS = _DOMAIN_UNADDRESSABLE_NEEDS


def player_skill_vector(row: pd.Series, league: pd.DataFrame) -> dict[str, float]:
    """Percentile (0..1) skill vector for one player against the scored population.

    A skill whose inputs are missing is **omitted**, not set to 0.5.

    `pct()` used to return 0.5 for an absent column *before ever touching the league
    series*, so a skill defined on a column that is not in the frame silently became
    exactly 0.5 for every player — no error, no warning, no test failure, and the UI
    would report the need as addressed while the skill contributed precisely nothing.
    Omission makes that failure detectable, and is what the no-constant-skill invariant
    in the regression charter checks for.
    """

    def pct(col: str) -> float | None:
        if col not in league.columns:
            return None
        value = pd.to_numeric(row.get(col), errors="coerce")
        if pd.isna(value):
            return None
        series = pd.to_numeric(league[col], errors="coerce").dropna()
        if series.empty:
            return None
        return float((series < value).mean())

    def pct_inv(col: str) -> float | None:
        """Percentile for a column where a LOW value is the good outcome.

        Every other skill reads "higher is better", and a skill vector is consumed as
        such: `fit_score` rewards a positive delta and `needs.NEED_TO_SKILL` assumes a
        need is addressed by more of the skill. Turnover rate runs the other way, and
        there was **no inversion mechanism in the skill path to copy** — the two
        inversions that exist are `needs.STAT_RULES`' `lower_is_need` flag, which acts on
        the team side, and a negative weight in `impact.INDEX_WEIGHTS`, which acts on a
        z-score rather than a percentile. Neither is reusable here, so the inversion is
        named rather than written as a bare `1 - pct(...)` at the call site, where a later
        edit could drop it silently.

        The mirror of `pct`'s `(series < value)`: the share of the league this player
        keeps the ball better than.
        """
        if col not in league.columns:
            return None
        value = pd.to_numeric(row.get(col), errors="coerce")
        if pd.isna(value):
            return None
        series = pd.to_numeric(league[col], errors="coerce").dropna()
        if series.empty:
            return None
        return float((series > value).mean())

    def blend(*parts: tuple[str, float]) -> float | None:
        """Weighted blend over the components that exist, renormalized to the survivors."""
        known = [(v, w) for col, w in parts if (v := pct(col)) is not None]
        if not known:
            return None
        total = sum(w for _, w in known)
        return sum(v * w for v, w in known) / total

    candidates: dict[str, float | None] = {
        # R4-1d. `shooting` was 0.5*pct(fg3a_rate) + 0.5*pct(TS_PCT), which answered two
        # different needs — "we do not shoot enough threes" and "we do not shoot them
        # well" — with one number. They are now separate skills, and volume is attempts
        # per minute rather than the old 3PA/FGA, which is shot *selection*: against the
        # quantity the `three_point_volume` need is actually built from, team 3PA per
        # game, attempts-per-minute tracks at rho +0.845 and 3PA/FGA at +0.754.
        "shooting_volume": pct("fg3a_per_min"),
        # Accuracy is empirical-Bayes shrunk before it is ranked. 37 % of player-seasons
        # have under 50 attempts and 219 sit at exactly 0.000 or 1.000, so an unshrunk
        # percentage ranks small-sample non-shooters at both extremes.
        "shooting_accuracy": blend(("fg3_pct_shrunk", 0.7), ("TS_PCT", 0.3)),
        "creation": pct("AST_PCT"),
        # Ball security is its own skill, not a synonym for creation (R4-1b). See
        # `needs.NEED_TO_SKILL` for the mapping this replaces and why it was backwards.
        "turnover_avoidance": pct_inv("TM_TOV_PCT"),
        # R4-1c/R4-2. `perimeter_defense = pct(stl_per_min)` served BOTH the
        # `defense_overall` and `point_of_attack_defense` needs, so a team told it
        # defended badly overall and a team told it could not contain a ball handler were
        # given the same answer, from steals alone. They are now two composites over
        # different terms — see `features.TEAM_DEFENSE_WEIGHTS` for what selected them.
        "team_defense": pct("team_defense_score"),
        "rim_protection": pct("blk_per_min"),
        "rebounding": blend(("DREB_PCT", 0.7), ("OREB_PCT", 0.3)),
        "size": pct("height_inches"),
        "scoring": pct("pts_per75"),
    }
    return {key: value for key, value in candidates.items() if value is not None}


@lru_cache(maxsize=1)
def skill_schema_fingerprint() -> str:
    """Identity of the skill-vector *contract*, for cache invalidation.

    `evaluation._skills()` caches the whole league's skill vectors under
    `cache.versioned_key("skills", ...)`, and that version namespace is bumped only by an
    ingestion run — never by a deploy. So a release that changes what a skill vector
    contains would keep serving the previous shape for the remainder of the six-hour TTL:
    new skills missing, renamed skills stale, no error anywhere. The failure cannot
    reproduce locally either, because the in-process fallback cache dies with the process
    while Redis, which production runs in a separate container, does not.

    Fingerprinting the declared keys, the function that computes them, and the feature
    list they read means the key changes exactly when the contract does.
    """
    payload = b"".join(
        (
            "|".join(SKILL_KEYS).encode(),
            inspect.getsource(player_skill_vector).encode(),
            repr(MODEL_FEATURES).encode(),
        )
    )
    return hashlib.sha256(payload).hexdigest()[:12]
