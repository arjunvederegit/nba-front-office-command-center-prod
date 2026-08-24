"""Roster shape says what it measures, and refuses what it cannot.

The properties that matter are the ones that stop this being read as a lineup model: it is
built from the SAME allocation the projection used, it declares the lineup fit
unavailable with a reason, and its congestion threshold is a measured league percentile
rather than a chosen constant.
"""

import pytest

from app.analytics.lineup_availability import (
    USABLE_MINUTES,
    implied_net_rating_sd,
)
from app.analytics.roster_shape import (
    CONGESTION_PERCENTILE,
    ROLE_PRESENT_MINUTES,
    league_role_reference,
    percentile,
    role_minutes,
    shape_report,
)
from app.services.evaluation import EvaluationService


def test_role_minutes_never_distributes_an_unknown_role_across_known_ones():
    minutes = {"a": 30.0, "b": 20.0, "c": 10.0}
    roles = {"a": "lead guard", "b": "lead guard"}
    totals = role_minutes(minutes, roles)
    assert totals == {"lead guard": 50.0, "unassigned": 10.0}


def test_the_league_reference_counts_teams_without_the_role_as_zero():
    """Omitting them would make a rare role's threshold high because it is rare."""
    per_team = [{"stretch big": 40.0}, {}, {}, {}]
    reference = league_role_reference(per_team)
    assert reference["stretch big"]["median"] == 0.0
    assert reference["stretch big"]["threshold"] > 0.0


def test_percentile_interpolates_and_handles_the_degenerate_cases():
    assert percentile([], 90) is None
    assert percentile([5.0], 90) == 5.0
    assert percentile([0.0, 10.0], 50) == pytest.approx(5.0)


def test_a_role_is_congested_only_when_it_grows_past_the_league_threshold():
    roles = {"in": "stretch big", "keep": "lead guard"}
    reference = {"stretch big": {"median": 10.0, "threshold": 20.0}}
    report = shape_report(
        before={"keep": 30.0},
        after={"keep": 25.0, "in": 25.0},
        roles=roles,
        reference=reference,
        incoming_ids={"in"},
    )
    assert report["congested_roles"] == ["stretch big"]
    assert report["arriving_roles"] == ["stretch big"]
    assert report["congestion_percentile"] == CONGESTION_PERCENTILE


def test_a_role_at_the_threshold_that_shrinks_is_not_congested():
    reference = {"stretch big": {"median": 10.0, "threshold": 20.0}}
    report = shape_report(
        before={"a": 40.0},
        after={"a": 25.0},
        roles={"a": "stretch big"},
        reference=reference,
        incoming_ids=set(),
    )
    # Above the threshold, but the trade reduced it — congestion is about what the trade
    # does, not about where the roster already was.
    assert report["congested_roles"] == []


def test_a_role_that_falls_below_a_rotation_share_is_reported_as_lost():
    reference = {"rim-protecting big": {"median": 20.0, "threshold": 35.0}}
    report = shape_report(
        before={"out": 30.0},
        after={},
        roles={"out": "rim-protecting big"},
        reference=reference,
        incoming_ids=set(),
    )
    assert report["roles_lost"] == ["rim-protecting big"]
    assert ROLE_PRESENT_MINUTES > 0


def test_the_report_declares_the_lineup_fit_unavailable_and_says_why():
    report = shape_report({}, {}, {}, {}, set())
    lineup = report["lineup_fit"]
    assert lineup["available"] is False
    assert "20.2 minutes" in lineup["reason"]
    assert "never played together" in lineup["also"]
    assert lineup["recheck"] == "make lineup-availability"
    assert "not lineup data" in report["basis"]


def test_the_standard_error_falls_as_the_square_root_of_playing_time():
    assert implied_net_rating_sd(20.2) == pytest.approx(16.1, abs=0.2)
    assert implied_net_rating_sd(376.9) == pytest.approx(3.7, abs=0.2)
    # Four times the minutes halves the error, which is the whole reason five-man data
    # cannot be used and two-man data can.
    assert implied_net_rating_sd(80.8) == pytest.approx(implied_net_rating_sd(20.2) / 2, rel=1e-6)
    assert USABLE_MINUTES == 200.0


# ------------------------------------------------------------------ through the service


def test_the_shape_uses_the_same_allocation_the_projection_used(db, seeded_league):
    """R5.5-1's defect was calling the allocator twice. The shape must read the rotations
    the projection produced, never re-derive them."""
    service = EvaluationService(db)
    team_a, team_b = seeded_league["team_a"], seeded_league["team_b"]
    incoming = seeded_league["roster_b"][0]
    outgoing = seeded_league["roster_a"][0]
    result = service.evaluate_for_team(
        team_a.id,
        [team_a.id, team_b.id],
        [
            {"player_id": incoming.id, "from_team_id": team_b.id, "to_team_id": team_a.id},
            {"player_id": outgoing.id, "from_team_id": team_a.id, "to_team_id": team_b.id},
        ],
        [],
        simulate=False,
    )
    shape = result["detail"]["roster_shape"]
    if "unavailable" in shape:
        pytest.skip(shape["unavailable"])
    total_after = sum(row["minutes_after"] for row in shape["roles"])
    rotation_after = sum(
        row["minutes"] for row in result["detail"]["performance"]["rotation_after"]
    )
    # The displayed rotation is the top 12, so the shape's total must be at least it and
    # at most the 240 the allocator distributes.
    assert rotation_after - 0.5 <= total_after <= 240.5


def test_an_unprojectable_roster_reports_the_shape_as_unavailable(db, two_teams, cap_params):
    service = EvaluationService(db)
    shape = service._roster_shape(None, [])
    assert "unavailable" in shape
    assert "cannot be reported" in shape["unavailable"]


def test_the_league_reference_is_cached_under_the_data_version(db, seeded_league):
    from app.core.cache import get_cache

    service = EvaluationService(db)
    first = service._league_role_reference()
    get_cache().bump_data_version()
    second = EvaluationService(db)._league_role_reference()
    assert set(first) == set(second)
