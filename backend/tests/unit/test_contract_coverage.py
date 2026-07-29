"""Roster-side contract coverage (R2a).

The metric the import naturally reports is the wrong one. A provider-side match rate
answers "how many rows in the file did we recognise" and can read 98 % while the question
the product needs answered — can we compute this team's payroll — is 60 %.

A *verified* payroll is all-or-nothing by design, so that metric is a cliff, not a slope.
The plan's measured sensitivity on the live 530-row roster: 1 % missing → 26/30 teams
with a payroll; 5 % → 10/30; 20 % → **0/30**.

R2c added the second metric this module now reports beside it: how many teams can
*disclose* a payroll as a lower bound with its coverage attached. The two must never be
conflated, so the tests below assert them separately on the same fixture — 0 verified and
2 disclosable, from the same 28-of-30 coverage.
"""

import pytest
from sqlalchemy.orm import Session

from app.ingestion.contract_coverage import contract_coverage, roster_side_unmatched, summarize
from tests.conftest import make_player


def test_reports_zero_coverage_and_says_why_with_no_contracts(
    db: Session, seeded_league: dict
) -> None:
    coverage = contract_coverage(db, "2025-26", "2027-28")
    assert coverage["roster_players_total"] == 30
    assert coverage["roster_players_with_salary_for_cap_league_year"] == 0
    assert coverage["teams_with_complete_payroll"] == 0
    assert coverage["cap_league_year_present_in_snapshot"] is False
    assert "not" in summarize(coverage, [])


def test_a_snapshot_for_the_wrong_league_year_is_called_out(
    db: Session, seeded_league: dict
) -> None:
    """The sharpest silent failure: every player covered, none for the year that governs
    trade legality. It looks like a complete success and yields no payroll at all."""
    coverage = contract_coverage(db, "2025-26", "2030-31")
    assert coverage["seasons_present_in_snapshot"] == ["2026-27"]
    assert coverage["cap_league_year_present_in_snapshot"] is False
    message = summarize(coverage, [])
    assert "2030-31" in message and "No team will have a payroll" in message


def test_one_missing_player_removes_that_team_from_the_count(
    db: Session, seeded_league: dict
) -> None:
    """The cliff, asserted. AAA[13] and BBB[13] have no contract in the fixture."""
    coverage = contract_coverage(db, "2025-26", "2026-27")
    assert coverage["roster_players_total"] == 30
    assert coverage["roster_players_with_salary_for_cap_league_year"] == 28
    assert coverage["roster_coverage_share"] == pytest.approx(28 / 30, abs=1e-4)
    # 93 % of players covered, and *zero* teams have a verified payroll.
    assert coverage["teams_with_complete_payroll"] == 0
    assert {t["team"] for t in coverage["teams_incomplete"]} == {"AAA", "BBB"}
    assert all(t["missing"] == 1 for t in coverage["teams_incomplete"])
    assert all(t["covered"] == 14 for t in coverage["teams_incomplete"])


def test_disclosable_and_verified_payroll_are_counted_separately(
    db: Session, seeded_league: dict
) -> None:
    """The R2c distinction, on the same fixture that shows the cliff. Both teams can show
    a payroll with coverage attached; neither can have one verified against a threshold."""
    coverage = contract_coverage(db, "2025-26", "2026-27")
    assert coverage["teams_with_disclosable_payroll"] == 2
    assert coverage["teams_with_complete_payroll"] == 0
    assert coverage["team_coverage_share_min"] == pytest.approx(14 / 15, abs=1e-4)

    message = summarize(coverage, [])
    assert "2/2 teams can show a payroll with disclosed coverage" in message
    assert "0/2 can have one verified" in message


def test_a_team_with_no_priced_contract_at_all_is_not_disclosable(
    db: Session, seeded_league: dict
) -> None:
    """Disclosure needs something to disclose: zero priced contracts is still nothing."""
    coverage = contract_coverage(db, "2025-26", "2029-30")  # no contract year exists
    assert coverage["teams_with_disclosable_payroll"] == 0
    assert coverage["teams_with_complete_payroll"] == 0


def test_a_fully_covered_team_is_counted(db: Session, seeded_league: dict) -> None:
    make_player(
        db,
        9999,
        "Fixture AAA 13 replacement",
        seeded_league["team_a"],
        salary=1_000_000,
    )
    # Give the previously-uncovered AAA player a contract by adding one for them.
    from app.db.models import Contract, ContractYear

    contract = Contract(
        player_id=seeded_league["no_contract_a"].id,
        contract_type="standard",
        source_name="test fixture",
    )
    db.add(contract)
    db.flush()
    db.add(ContractYear(contract_id=contract.id, season="2026-27", salary=2_000_000))
    db.commit()

    coverage = contract_coverage(db, "2025-26", "2026-27")
    assert coverage["teams_with_complete_payroll"] == 1
    assert [t["team"] for t in coverage["teams_incomplete"]] == ["BBB"]


def test_the_uncovered_list_is_roster_side_and_names_the_reason(
    db: Session, seeded_league: dict
) -> None:
    rows = roster_side_unmatched(db, "2025-26", "2026-27")
    assert {r["player"] for r in rows} == {
        seeded_league["no_contract_a"].full_name,
        seeded_league["no_contract_b"].full_name,
    }
    assert all(r["reason"] == "no contract on file" for r in rows)
    assert {r["team"] for r in rows} == {"AAA", "BBB"}


def test_a_contract_without_the_right_year_is_distinguished_from_no_contract(
    db: Session, seeded_league: dict
) -> None:
    """'has a deal that expired' and 'we have no data' are different problems and get
    different messages."""
    from app.db.models import Contract, ContractYear

    contract = Contract(
        player_id=seeded_league["no_contract_a"].id,
        contract_type="standard",
        source_name="test fixture",
    )
    db.add(contract)
    db.flush()
    db.add(ContractYear(contract_id=contract.id, season="2025-26", salary=2_000_000))
    db.commit()

    rows = roster_side_unmatched(db, "2025-26", "2026-27")
    reasons = {r["player"]: r["reason"] for r in rows}
    assert reasons[seeded_league["no_contract_a"].full_name] == (
        "contract on file but no 2026-27 year"
    )
    assert reasons[seeded_league["no_contract_b"].full_name] == "no contract on file"
