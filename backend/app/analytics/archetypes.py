"""Player archetypes from real statistical profiles.

K-means over standardized role features; cluster labels are assigned from cluster
centers by deterministic rules (never arbitrarily). Silhouette score is recorded with
the model version so clustering quality is inspectable."""

import hashlib
import inspect
from functools import lru_cache

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from .features import MODEL_FEATURES, RANDOM_SEED

ARCHETYPE_FEATURES = [
    "USG_PCT",
    "AST_PCT",
    "fg3a_rate",
    "TS_PCT",
    "OREB_PCT",
    "DREB_PCT",
    "stl_per_min",
    "blk_per_min",
    "pts_per75",
    "height_inches",
]

N_CLUSTERS = 8


def _label_from_center(center: dict[str, float], league: dict[str, float]) -> str:
    """Deterministic labeling: compare the cluster center to league medians."""
    high = {k: center[k] > league[k] for k in center}
    tall = center["height_inches"] >= league["height_inches"] + 2
    small = center["height_inches"] <= league["height_inches"] - 2

    if high["USG_PCT"] and high["AST_PCT"]:
        return "primary creator"
    if high["AST_PCT"] and not high["USG_PCT"]:
        return "secondary creator"
    if tall and high["blk_per_min"] and not high["fg3a_rate"]:
        return "rim-running center"
    if tall and high["fg3a_rate"]:
        return "stretch big"
    if tall and high["DREB_PCT"]:
        return "defensive big"
    if high["fg3a_rate"] and high["TS_PCT"] and not high["USG_PCT"]:
        return "movement shooter"
    if high["stl_per_min"] and high["fg3a_rate"]:
        return "two-way wing"
    if high["USG_PCT"] and not high["AST_PCT"]:
        return "bench scorer"
    if small and high["stl_per_min"]:
        return "point-of-attack guard"
    return "role player"


def fit_archetypes(weighted: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Cluster recency-weighted player features. Returns (assignments, metadata)."""
    df = weighted.copy()
    features = [f for f in ARCHETYPE_FEATURES if f in df.columns]
    matrix = df[features].apply(pd.to_numeric, errors="coerce")
    mask = matrix.notna().sum(axis=1) >= len(features) - 2
    df = df[mask]
    matrix = matrix[mask].fillna(matrix.median(numeric_only=True))

    if len(df) < N_CLUSTERS * 3:
        return pd.DataFrame(), {"note": "insufficient players for clustering"}

    scaler = StandardScaler()
    X = scaler.fit_transform(matrix.to_numpy())
    kmeans = KMeans(n_clusters=N_CLUSTERS, random_state=RANDOM_SEED, n_init=10)
    clusters = kmeans.fit_predict(X)
    silhouette = float(silhouette_score(X, clusters))

    league_medians = {f: float(matrix[f].median()) for f in features}
    centers_raw = scaler.inverse_transform(kmeans.cluster_centers_)
    labels: dict[int, str] = {}
    for idx, center in enumerate(centers_raw):
        center_map = dict(zip(features, [float(v) for v in center], strict=False))
        labels[idx] = _label_from_center(center_map, league_medians)

    # Disambiguate duplicate labels deterministically
    seen: dict[str, int] = {}
    for idx in sorted(labels):
        base = labels[idx]
        seen[base] = seen.get(base, 0) + 1
        if seen[base] > 1:
            labels[idx] = f"{base} ({seen[base]})"

    distances = kmeans.transform(X)
    out = pd.DataFrame(
        {
            "player_id": df["player_id"].to_numpy(),
            "cluster_id": clusters,
            "label": [labels[c] for c in clusters],
            "distance": distances[np.arange(len(clusters)), clusters],
        }
    )
    meta = {
        "n_clusters": N_CLUSTERS,
        "silhouette": silhouette,
        "features": features,
        "labels": {str(k): v for k, v in labels.items()},
        "centers": {
            str(i): dict(zip(features, [round(float(v), 4) for v in center], strict=False))
            for i, center in enumerate(centers_raw)
        },
    }
    return out, meta


# Skill dimensions used by roster-fit; derived from the same feature space so that
# team needs and player skills are directly comparable.
SKILL_KEYS = [
    "shooting_volume",
    "shooting_accuracy",
    "creation",
    "turnover_avoidance",
    "team_defense",
    "rim_protection",
    "rebounding",
    "size",
    "scoring",
]

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
UNADDRESSABLE_NEEDS = {
    "point_of_attack_defense": (
        "no player skill claims to address this: on-ball defence cannot be measured from "
        "box-score data, and a steals-based proxy rates ball-dominant guards above the "
        "defenders who actually guard them"
    ),
}


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
