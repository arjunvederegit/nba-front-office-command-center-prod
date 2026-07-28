"""The candidate generator is hidden (R1-8) but still reachable via the API, so what it
does and does not search must be stated in the response rather than inferred from
`evaluations_run`.

W8/QA-10: it reaches **13.8 %** of counterparties (4 of 29), not the ~21 % first
estimated, and says nothing about the truncation.
"""

from sqlalchemy.orm import Session

from app.services.candidates import generate_candidates


def test_response_states_what_was_searched(db: Session, seeded_league: dict) -> None:
    result = generate_candidates(db, seeded_league["team_a"].id, strategy="contend")
    coverage = result["coverage"]
    assert coverage["counterparties_total"] == 1  # only BBB exists in the fixture
    assert coverage["counterparties_searched"] <= coverage["counterparties_total"]
    assert coverage["share_searched"] is not None
    assert set(coverage["searched"]) | set(coverage["not_searched"]) == {"BBB"}
    assert "EXPERIMENTAL" in result["note"]
    assert "no salary matching" in result["note"]


def test_counterparties_are_searched_in_a_deterministic_order(
    db: Session, seeded_league: dict
) -> None:
    """Insertion order made the truncated sweep irreproducible between runs."""
    first = generate_candidates(db, seeded_league["team_a"].id, strategy="contend")
    second = generate_candidates(db, seeded_league["team_a"].id, strategy="contend")
    assert first["coverage"]["searched"] == second["coverage"]["searched"]
    assert first["coverage"]["searched"] == sorted(first["coverage"]["searched"])
