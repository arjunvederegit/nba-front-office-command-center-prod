"""The acquisition battery runs, and its team-type classification is measured.

The live numbers are in the R6 report; what is asserted here is that the classification
comes from data rather than from a label, and that a threshold failure is reported.
"""

import pytest
from sqlalchemy import select

from app.db.models import Standing, TeamNeed
from app.services.acquisition_validation import (
    THRESHOLDS,
    WEAKNESS_FAMILY,
    _concentration,
    _jaccard,
    _tertile_class,
    run_battery,
)
from app.services.evaluation import EvaluationService


def test_tertile_classes_come_from_the_distribution_not_a_label():
    cuts = (0.4, 0.6)
    names = ("rebuilding", "middle", "contender")
    assert _tertile_class(0.30, cuts, names) == "rebuilding"
    assert _tertile_class(0.50, cuts, names) == "middle"
    assert _tertile_class(0.70, cuts, names) == "contender"
    assert _tertile_class(None, cuts, names) == "unknown"


def test_concentration_is_the_top_twos_share_of_above_replacement_value(db, seeded_league):
    service = EvaluationService(db)
    share = _concentration(service, seeded_league["team_a"].id)
    assert share is not None
    assert 0.0 < share <= 1.0


def test_concentration_is_unknown_rather_than_zero_on_a_roster_with_no_value(db, two_teams):
    service = EvaluationService(db)
    assert _concentration(service, two_teams[0].id) is None


def test_every_need_maps_to_a_weakness_family(db, seeded_league):
    for need in db.scalars(select(TeamNeed)).all():
        assert need.need_key in WEAKNESS_FAMILY


def test_jaccard_handles_the_empty_cases():
    assert _jaccard([], []) == 1.0
    assert _jaccard(["a"], []) == 0.0
    assert _jaccard(["a", "b"], ["b", "c"]) == pytest.approx(1 / 3)


def test_the_battery_runs_over_a_seeded_league_and_reports_every_check(db, seeded_league):
    db.add_all(
        [
            Standing(
                team_id=team.id,
                season="2025-26",
                wins=41 + offset,
                losses=41 - offset,
                win_pct=(41 + offset) / 82,
                conference="East",
            )
            for offset, team in enumerate((seeded_league["team_a"], seeded_league["team_b"]))
        ]
    )
    db.commit()
    report = run_battery(db, k=3)
    names = {c["name"] for c in report["checks"]}
    assert "need_filter_differentiates" in names
    assert "shuffled_need_null" in names
    assert report["teams"] == 2
    assert set(report["by_team_type"]) == {"direction", "concentration_class", "weakness"}
    for check in report["checks"]:
        assert (check["threshold"] is None) == (check["passed"] is None)


def test_a_failing_threshold_is_listed(db, seeded_league, monkeypatch):
    monkeypatch.setitem(THRESHOLDS, "distinct_target_ratio_min", 99.0)
    report = run_battery(db, k=3)
    assert "need_filter_differentiates" in report["failed"]
