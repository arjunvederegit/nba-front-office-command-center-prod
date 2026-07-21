"""Player archetypes from real statistical profiles.

K-means over standardized role features; cluster labels are assigned from cluster
centers by deterministic rules (never arbitrarily). Silhouette score is recorded with
the model version so clustering quality is inspectable."""

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from .features import RANDOM_SEED

ARCHETYPE_FEATURES = [
    "USG_PCT", "AST_PCT", "fg3a_rate", "TS_PCT", "OREB_PCT", "DREB_PCT",
    "stl_per_min", "blk_per_min", "pts_per75", "height_inches",
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
    "shooting", "creation", "perimeter_defense", "rim_protection", "rebounding", "size", "scoring",
]


def player_skill_vector(row: pd.Series, league: pd.DataFrame) -> dict[str, float]:
    """Percentile (0..1) skill vector for one player against the scored population."""

    def pct(col: str) -> float:
        value = pd.to_numeric(row.get(col), errors="coerce")
        if pd.isna(value):
            return 0.5
        series = pd.to_numeric(league[col], errors="coerce").dropna()
        if series.empty:
            return 0.5
        return float((series < value).mean())

    return {
        "shooting": pct("fg3a_rate") * 0.5 + pct("TS_PCT") * 0.5,
        "creation": pct("AST_PCT"),
        "perimeter_defense": pct("stl_per_min"),
        "rim_protection": pct("blk_per_min"),
        "rebounding": pct("DREB_PCT") * 0.7 + pct("OREB_PCT") * 0.3,
        "size": pct("height_inches"),
        "scoring": pct("pts_per75"),
    }
