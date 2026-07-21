"""Training pipeline: features → impact model comparison → archetypes → persistence.

Every trained artifact is recorded in model_versions with its algorithm, features,
target, validation metrics, and training window. Random seeds are fixed for
reproducibility."""

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR, get_settings
from app.core.logging import get_logger
from app.db.models import (
    ModelVersion,
    PlayerArchetype,
    PlayerImpactEstimate,
    RosterEntry,
    Standing,
    TeamSeasonStats,
)

from .archetypes import fit_archetypes
from .availability import availability_from_history
from .features import build_player_season_features, recency_weighted_features
from .impact import TEI_SCALE, score_players, train_impact_models
from .projection import calibrate_wins_per_net_rating

logger = get_logger(__name__)
ARTIFACT_DIR = BACKEND_DIR.parent / "models" / "artifacts"


def _code_commit() -> str | None:
    try:
        return (
            subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, cwd=BACKEND_DIR, timeout=5,
            ).stdout.strip()
            or None
        )
    except Exception:
        return None


def _register_model(
    db: Session, name: str, version: str, algorithm: str, training_period: str,
    features: list[str], target: str | None, metrics: dict, artifact_path: str | None,
) -> ModelVersion:
    for old in db.scalars(
        select(ModelVersion).where(ModelVersion.model_name == name, ModelVersion.is_active)
    ).all():
        old.is_active = False
    model = ModelVersion(
        model_name=name,
        version=version,
        algorithm=algorithm,
        training_period=training_period,
        feature_list=features,
        target=target,
        validation_metrics=metrics,
        artifact_path=artifact_path,
        trained_at=datetime.now(UTC),
        code_commit=_code_commit(),
        is_active=True,
    )
    db.add(model)
    db.flush()
    return model


def train_all(db: Session) -> dict[str, Any]:
    settings = get_settings()
    seasons = settings.history_season_list
    version = datetime.now(UTC).strftime("v%Y%m%d%H%M")
    training_period = f"{seasons[0]}..{seasons[-1]}"

    season_df = build_player_season_features(db)
    if season_df.empty:
        return {"error": "no ingested player stats; run `make sync-data` first"}

    result = train_impact_models(season_df, seasons)

    artifact_path = None
    if result.ridge is not None:
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        artifact_file = ARTIFACT_DIR / f"impact_ridge_{version}.joblib"
        joblib.dump({"model": result.ridge, "features": result.feature_names}, artifact_file)
        artifact_path = str(artifact_file.relative_to(BACKEND_DIR.parent))

    impact_model = _register_model(
        db,
        name="player_impact",
        version=version,
        algorithm=result.algorithm,
        training_period=training_period,
        features=result.feature_names,
        target=result.validation.get("target") if isinstance(result.validation, dict) else None,
        metrics={**result.validation, "chosen_model": result.chosen_model,
                 "coefficients": {k: round(float(v), 4) for k, v in result.coefficients.items()}},
        artifact_path=artifact_path,
    )

    # Score current players: recency-weighted window features
    weighted = recency_weighted_features(season_df, seasons)
    scored = score_players(weighted, result, season_df)

    availability = availability_from_history(season_df, seasons).set_index("player_id")
    rostered_ids = {
        r.player_id
        for r in db.scalars(select(RosterEntry).where(RosterEntry.is_current)).all()
    }

    written = 0
    for _, row in scored.iterrows():
        player_id = row["player_id"]
        if rostered_ids and player_id not in rostered_ids and not row.get("is_active"):
            continue
        avail = (
            float(availability.loc[player_id, "availability"])
            if player_id in availability.index
            else None
        )
        existing = db.scalar(
            select(PlayerImpactEstimate).where(
                PlayerImpactEstimate.player_id == player_id,
                PlayerImpactEstimate.season == settings.current_season,
                PlayerImpactEstimate.model_version_id == impact_model.id,
            )
        )
        values = {
            "player_id": player_id,
            "season": settings.current_season,
            "model_version_id": impact_model.id,
            "tei": float(row["tei"]),
            "tei_offense": float(row["tei_offense"]),
            "tei_defense": float(row["tei_defense"]),
            "tei_low": float(row["tei_low"]),
            "tei_high": float(row["tei_high"]),
            "availability": avail,
            "minutes_estimate": float(row["MIN"]) if pd.notna(row.get("MIN")) else None,
            "inputs": {
                "seasons_observed": int(row["seasons_observed"]),
                "total_minutes_window": float(row["total_minutes_window"]),
                "scale": TEI_SCALE,
            },
        }
        if existing is None:
            db.add(PlayerImpactEstimate(**values))
        else:
            for k, v in values.items():
                setattr(existing, k, v)
        written += 1

    # Archetypes
    assignments, archetype_meta = fit_archetypes(scored)
    archetype_written = 0
    if not assignments.empty:
        _register_model(
            db,
            name="player_archetype",
            version=version,
            algorithm=f"k-means (k={archetype_meta['n_clusters']})",
            training_period=training_period,
            features=archetype_meta["features"],
            target=None,
            metrics={"silhouette": archetype_meta["silhouette"], "labels": archetype_meta["labels"]},
            artifact_path=None,
        )
        for _, row in assignments.iterrows():
            existing = db.scalar(
                select(PlayerArchetype).where(
                    PlayerArchetype.player_id == row["player_id"],
                    PlayerArchetype.season == settings.current_season,
                )
            )
            values = {
                "player_id": row["player_id"],
                "season": settings.current_season,
                "cluster_id": int(row["cluster_id"]),
                "label": str(row["label"]),
                "distances": {"own_cluster": round(float(row["distance"]), 3)},
            }
            if existing is None:
                db.add(PlayerArchetype(**values))
            else:
                for k, v in values.items():
                    setattr(existing, k, v)
            archetype_written += 1

    # Wins-per-net-rating calibration from ingested team seasons
    team_rows = []
    for stats in db.scalars(
        select(TeamSeasonStats).where(TeamSeasonStats.stat_type == "advanced")
    ).all():
        standing = db.scalar(
            select(Standing).where(
                Standing.team_id == stats.team_id, Standing.season == stats.season
            )
        )
        net = (stats.stats or {}).get("NET_RATING")
        if standing is not None and net is not None:
            team_rows.append({"net_rating": float(net), "wins": standing.wins})
    mapping = calibrate_wins_per_net_rating(pd.DataFrame(team_rows))
    _register_model(
        db,
        name="team_projection",
        version=version,
        algorithm="linear wins ~ net_rating",
        training_period=training_period,
        features=["NET_RATING"],
        target="team regular-season wins",
        metrics=mapping,
        artifact_path=None,
    )

    db.commit()
    summary = {
        "version": version,
        "impact": {"chosen": result.chosen_model, "players_scored": written,
                   "validation": result.validation},
        "archetypes": {"players_labeled": archetype_written,
                       "silhouette": archetype_meta.get("silhouette")},
        "wins_mapping": mapping,
    }
    logger.info("training complete: %s", summary["version"])
    return summary
