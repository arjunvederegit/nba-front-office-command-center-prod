"""TradeLab Estimated Impact (TEI).

TEI is this project's own portfolio-model estimate of per-100-possession player impact.
It is NOT RAPTOR, EPM, LEBRON, BPM, or any proprietary metric, and it is documented as
an estimate with uncertainty (see docs/model-card-player-impact.md).

Two candidates are trained and compared with time-aware validation (no row-level
random splits across seasons — transitions only ever predict forward):

1. Baseline: a transparent weighted z-score index (documented fixed weights).
2. Challenger: ridge regression predicting a next-season box-derived impact proxy
   (minutes-weighted blend of z(PIE) and z(NET_RATING)) from current-season features.

The production choice is made on held-out MAE and documented in model_versions."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error

from .features import RANDOM_SEED, zscore_by_season

# Transparent baseline index weights (documented in docs/methodology.md).
INDEX_WEIGHTS: dict[str, float] = {
    "z_pts_per75": 0.22,
    "z_TS_PCT": 0.18,
    "z_AST_PCT": 0.14,
    "z_TM_TOV_PCT": -0.08,
    "z_USG_PCT": 0.06,
    "z_OREB_PCT": 0.04,
    "z_DREB_PCT": 0.08,
    "z_stl_per_min": 0.12,
    "z_blk_per_min": 0.10,
    "z_PIE": 0.14,
}

OFFENSE_KEYS = ["z_pts_per75", "z_TS_PCT", "z_AST_PCT", "z_TM_TOV_PCT", "z_USG_PCT", "z_OREB_PCT"]
DEFENSE_KEYS = ["z_DREB_PCT", "z_stl_per_min", "z_blk_per_min"]

RIDGE_FEATURES = [
    "z_pts_per75",
    "z_TS_PCT",
    "z_USG_PCT",
    "z_AST_PCT",
    "z_TM_TOV_PCT",
    "z_OREB_PCT",
    "z_DREB_PCT",
    "z_stl_per_min",
    "z_blk_per_min",
    "z_fg3a_rate",
    "z_fta_rate",
    "z_MIN",
    "z_PIE",
    "z_NET_RATING",
    "AGE",
]

Z_SOURCE_COLS = [
    "pts_per75",
    "TS_PCT",
    "USG_PCT",
    "AST_PCT",
    "TM_TOV_PCT",
    "OREB_PCT",
    "DREB_PCT",
    "stl_per_min",
    "blk_per_min",
    "fg3a_rate",
    "fta_rate",
    "MIN",
    "PIE",
    "NET_RATING",
]

TEI_SCALE = 2.5  # index points per z-unit; elite seasons land around +5


def add_zscores(df: pd.DataFrame) -> pd.DataFrame:
    for col in Z_SOURCE_COLS:
        if col in df.columns:
            df = zscore_by_season(df, col)
    return df


def baseline_index(df: pd.DataFrame) -> pd.Series:
    """Weighted z-score index on the TEI scale."""
    total = pd.Series(np.zeros(len(df)), index=df.index)
    for key, weight in INDEX_WEIGHTS.items():
        if key in df.columns:
            total = total + weight * pd.to_numeric(df[key], errors="coerce").fillna(0.0)
    return total * TEI_SCALE / sum(abs(w) for w in INDEX_WEIGHTS.values())


def component_index(df: pd.DataFrame, keys: list[str]) -> pd.Series:
    total = pd.Series(np.zeros(len(df)), index=df.index)
    weight_sum = 0.0
    for key in keys:
        weight = INDEX_WEIGHTS.get(key, 0.0)
        if key in df.columns and weight:
            total = total + weight * pd.to_numeric(df[key], errors="coerce").fillna(0.0)
            weight_sum += abs(weight)
    return total * TEI_SCALE / weight_sum if weight_sum else total


def build_target(df: pd.DataFrame) -> pd.Series:
    """Next-season impact proxy: minutes-weighted blend of z(PIE) and z(NET_RATING)."""
    z_pie = pd.to_numeric(df.get("z_PIE"), errors="coerce").fillna(0.0)
    z_net = pd.to_numeric(df.get("z_NET_RATING"), errors="coerce").fillna(0.0)
    return 0.6 * z_pie + 0.4 * z_net


@dataclass
class ImpactTrainingResult:
    chosen_model: str
    algorithm: str
    validation: dict
    coefficients: dict
    ridge: Ridge | None
    feature_names: list[str]


def _make_transitions(df: pd.DataFrame, seasons: list[str]) -> pd.DataFrame:
    """Pairs (features in season s, target in season s+1) for the same player."""
    frames = []
    for current, following in zip(seasons[:-1], seasons[1:], strict=False):
        cur = df[df["season"] == current].set_index("player_id")
        nxt = df[df["season"] == following].set_index("player_id")
        joined = cur.join(nxt[["target"]].rename(columns={"target": "target_next"}), how="inner")
        joined = joined.dropna(subset=["target_next"])
        joined["transition"] = f"{current}->{following}"
        frames.append(joined.reset_index())
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def train_impact_models(df: pd.DataFrame, seasons: list[str]) -> ImpactTrainingResult:
    """Time-aware training: earliest transition trains, latest transition validates."""
    df = add_zscores(df.copy())
    df["target"] = build_target(df)
    df["baseline_tei"] = baseline_index(df)

    transitions = _make_transitions(df, seasons)
    features = [f for f in RIDGE_FEATURES if f in transitions.columns]

    validation: dict = {"note": "insufficient transitions for supervised validation"}
    ridge: Ridge | None = None
    chosen = "baseline_index"
    algorithm = "weighted z-score index"
    coefficients: dict = dict(INDEX_WEIGHTS)

    if not transitions.empty and transitions["transition"].nunique() >= 2:
        transition_names = sorted(transitions["transition"].unique())
        train_mask = transitions["transition"].isin(transition_names[:-1])
        valid_mask = transitions["transition"] == transition_names[-1]
        X_train = transitions.loc[train_mask, features].fillna(0.0).to_numpy()
        y_train = transitions.loc[train_mask, "target_next"].to_numpy()
        X_valid = transitions.loc[valid_mask, features].fillna(0.0).to_numpy()
        y_valid = transitions.loc[valid_mask, "target_next"].to_numpy()

        ridge = Ridge(alpha=10.0, random_state=RANDOM_SEED)
        ridge.fit(X_train, y_train)
        ridge_pred = ridge.predict(X_valid)

        # Baselines: persistence (this season's target repeats) and the index.
        persistence_pred = transitions.loc[valid_mask, "target"].fillna(0.0).to_numpy()
        index_pred = (transitions.loc[valid_mask, "baseline_tei"] / TEI_SCALE).to_numpy()

        residual_std = float(np.std(y_valid - ridge.predict(X_valid)))
        validation = {
            "train_transition": transition_names[:-1],
            "validation_transition": transition_names[-1],
            "n_train": int(train_mask.sum()),
            "n_valid": int(valid_mask.sum()),
            "ridge_mae": float(mean_absolute_error(y_valid, ridge_pred)),
            "persistence_mae": float(mean_absolute_error(y_valid, persistence_pred)),
            "index_mae": float(mean_absolute_error(y_valid, index_pred)),
            "ridge_residual_std": residual_std,
            "target": "next-season 0.6*z(PIE) + 0.4*z(NET_RATING), minutes-weighted z within season",
        }
        if validation["ridge_mae"] <= min(validation["persistence_mae"], validation["index_mae"]):
            chosen = "ridge"
            algorithm = "ridge regression (alpha=10, time-aware split)"
            coefficients = dict(zip(features, [float(c) for c in ridge.coef_], strict=False))

    return ImpactTrainingResult(
        chosen_model=chosen,
        algorithm=algorithm,
        validation=validation,
        coefficients=coefficients,
        ridge=ridge if chosen == "ridge" else None,
        feature_names=features,
    )


def score_players(
    weighted: pd.DataFrame, result: ImpactTrainingResult, season_df: pd.DataFrame
) -> pd.DataFrame:
    """Score recency-weighted current-player features with the chosen model.

    Returns TEI on the index scale plus offense/defense sub-components and an
    uncertainty band from validation residuals (documented approximation)."""
    # z-score the weighted frame against the latest season's distribution
    weighted = weighted.copy()
    weighted["season"] = "window"
    weighted["total_minutes"] = weighted["total_minutes_window"]
    weighted = add_zscores(weighted)

    if result.chosen_model == "ridge" and result.ridge is not None:
        X = weighted[list(result.feature_names)].fillna(0.0).to_numpy()
        tei = result.ridge.predict(X) * TEI_SCALE
    else:
        tei = baseline_index(weighted).to_numpy()

    weighted["tei"] = tei
    weighted["tei_offense"] = component_index(weighted, OFFENSE_KEYS)
    weighted["tei_defense"] = component_index(weighted, DEFENSE_KEYS)

    residual_std = 0.6
    if isinstance(result.validation, dict) and result.validation.get("ridge_residual_std"):
        residual_std = float(result.validation["ridge_residual_std"])
    band = 1.2816 * residual_std * TEI_SCALE  # 10th/90th percentile under normal residuals
    weighted["tei_low"] = weighted["tei"] - band
    weighted["tei_high"] = weighted["tei"] + band
    return weighted
