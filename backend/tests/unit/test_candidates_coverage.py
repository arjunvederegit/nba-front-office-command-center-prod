"""The candidate generator's response must state what it searched, rather than leaving it
to be inferred from `evaluations_run`.

W8/QA-10: at R1 it reached **13.8 %** of counterparties (4 of 29) and said nothing about
the truncation. R5-3 divides the evaluation budget across the whole league instead of
letting the first few teams consume it, so coverage is now complete by construction —
and the truncation that remains happens *inside* a counterparty and is reported per team.
"""

from sqlalchemy.orm import Session

from app.services.candidates import generate_candidates


def test_response_states_what_was_searched(db: Session, seeded_league: dict) -> None:
    result = generate_candidates(db, seeded_league["team_a"].id, strategy="contend")
    coverage = result["coverage"]
    assert coverage["counterparties_total"] == 1  # only BBB exists in the fixture
    assert coverage["counterparties_searched"] == coverage["counterparties_total"]
    assert coverage["share_searched"] == 1.0
    assert set(coverage["searched"]) | set(coverage["not_searched"]) == {"BBB"}
    assert "EXPERIMENTAL" in result["note"]
    # Salary matching is applied now, and the response says on what and where it could not
    # be: the old note's flat "applies no salary matching" is no longer true.
    assert "counterparties were searched" in result["note"]
    matching = coverage["salary_matching"]
    assert matching["pairs_checked"] + matching["pairs_skipped_unknown_salaries"] > 0
    assert "Expanded-TPE bands" in matching["note"]


def test_counterparties_are_searched_in_a_deterministic_order(
    db: Session, seeded_league: dict
) -> None:
    """Insertion order made the truncated sweep irreproducible between runs."""
    first = generate_candidates(db, seeded_league["team_a"].id, strategy="contend")
    second = generate_candidates(db, seeded_league["team_a"].id, strategy="contend")
    assert first["coverage"]["searched"] == second["coverage"]["searched"]
    assert first["coverage"]["searched"] == sorted(first["coverage"]["searched"])
