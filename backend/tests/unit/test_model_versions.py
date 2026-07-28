"""Model-version identity and the estimate garbage collector (R1-9).

`train_all` stamped every model in a run with one
`datetime.now().strftime("v%Y%m%d%H%M")`, so `model_versions` held `v202607210204`
three times per model and a version string could not identify a model. Nothing removed
superseded estimates either: 1,536 rows for 512 players across three versions, growing
by 512 on every `make train && make score`.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics.train import _content_version, _gc_superseded_estimates, _register_model
from app.db.models import ModelVersion, Player, PlayerImpactEstimate


def _register(db: Session, name: str, metrics: dict) -> ModelVersion:
    return _register_model(
        db,
        name=name,
        version="ignored — recomputed from content",
        algorithm="test",
        training_period="2023-24..2025-26",
        features=["a", "b"],
        target="t",
        metrics=metrics,
        artifact_path=None,
    )


def test_models_trained_in_the_same_run_get_different_versions(db: Session) -> None:
    impact = _register(db, "player_impact", {"mae": 0.6374})
    archetype = _register(db, "player_archetype", {"silhouette": 0.156})
    projection = _register(db, "team_projection", {"slope": 2.235})
    db.commit()
    versions = {impact.version, archetype.version, projection.version}
    assert len(versions) == 3, f"a run produced colliding version strings: {versions}"


def test_an_identical_retrain_reuses_the_row(db: Session) -> None:
    first = _register(db, "player_impact", {"mae": 0.6374})
    db.commit()
    second = _register(db, "player_impact", {"mae": 0.6374})
    db.commit()
    assert first.id == second.id
    assert db.scalar(select(func.count()).select_from(ModelVersion)) == 1
    assert second.is_active is True


def test_a_changed_model_gets_a_new_version(db: Session) -> None:
    first = _register(db, "player_impact", {"mae": 0.6374})
    db.commit()
    second = _register(db, "player_impact", {"mae": 0.5911})
    db.commit()
    assert first.version != second.version
    assert first.is_active is False and second.is_active is True


def test_version_is_stable_against_float_noise() -> None:
    a = _content_version("m", "ridge", "p", ["x"], {"mae": 0.63740000001})
    b = _content_version("m", "ridge", "p", ["x"], {"mae": 0.6374})
    assert a == b


def test_superseded_estimates_are_garbage_collected(db: Session) -> None:
    now = datetime.now(UTC)
    old = ModelVersion(
        model_name="player_impact",
        version="old",
        algorithm="test",
        trained_at=now - timedelta(days=1),
        is_active=False,
    )
    current = ModelVersion(
        model_name="player_impact",
        version="current",
        algorithm="test",
        trained_at=now,
        is_active=True,
    )
    db.add_all([old, current])
    db.flush()
    player = Player(nba_player_id=1, full_name="Fixture Player", is_active=True)
    db.add(player)
    db.flush()
    for version, tei in ((old, 1.0), (current, 1.4)):
        db.add(
            PlayerImpactEstimate(
                player_id=player.id,
                season="2025-26",
                model_version_id=version.id,
                tei=tei,
            )
        )
    db.commit()
    assert db.scalar(select(func.count()).select_from(PlayerImpactEstimate)) == 2

    removed = _gc_superseded_estimates(db)
    db.commit()
    assert removed == 1
    surviving = db.scalars(select(PlayerImpactEstimate)).all()
    assert len(surviving) == 1
    assert surviving[0].tei == pytest.approx(1.4)
    # The superseded *model version* is kept — it is the provenance record.
    assert db.scalar(select(func.count()).select_from(ModelVersion)) == 2
