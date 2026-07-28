"""Test entities must not live in a database that holds real provider data.

`CONTRIBUTING.md` rule 1 requires fixtures to live only under `backend/tests`, and no
document disclosed that the development database held 22 trade proposals, 16 scenarios
and 50 comparison sets from repeated runs — `E2E RosterLab deal`, `Smoke test deal`,
`probe`. The end-to-end suite now runs against its own database (`make seed-demo`);
`purge-fixtures` clears what earlier runs left behind.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ComparisonSet, Scenario, TradeProposal, TradeTeam
from app.ingestion.fixtures import FIXTURE_NAME, find_fixture_entities, purge_fixtures


def _seed(db: Session, team_id: str) -> None:
    db.add(Scenario(name="E2E scenario", focal_team_id=team_id, strategy="contend"))
    db.add(Scenario(name="BOS — Contend now", focal_team_id=team_id, strategy="contend"))
    trade = TradeProposal(name="E2E RosterLab deal")
    keeper = TradeProposal(name="Tatum for Brown swap")
    db.add_all([trade, keeper])
    db.flush()
    db.add(TradeTeam(trade_id=trade.id, team_id=team_id))
    db.add(ComparisonSet(name="probe", trade_ids=[trade.id, keeper.id]))
    db.add(ComparisonSet(name="Deadline shortlist", trade_ids=[keeper.id]))
    db.commit()


def test_the_pattern_matches_automated_names_only() -> None:
    for automated in ("E2E scenario", "Smoke test deal", "probe", "Fixture Alpha", "TEST deal"):
        assert FIXTURE_NAME.search(automated), automated
    # Names a person would plausibly choose for real work must survive.
    for real in (
        "BOS — Contend now",
        "Deadline shortlist",
        "Tatum for Brown swap",
        "Protest the Latest",  # contains "test" only inside a word
        "Contest window",
    ):
        assert not FIXTURE_NAME.search(real), real


def test_dry_run_reports_without_deleting(db: Session, seeded_league: dict) -> None:
    _seed(db, seeded_league["team_a"].id)
    before = db.scalars(select(TradeProposal)).all()
    summary = purge_fixtures(db)
    assert summary["dry_run"] is True
    assert summary["counts"] == {"scenarios": 1, "trades": 1, "comparisons": 1}
    assert len(db.scalars(select(TradeProposal)).all()) == len(before)


def test_apply_removes_only_the_automated_entities(db: Session, seeded_league: dict) -> None:
    _seed(db, seeded_league["team_a"].id)
    purge_fixtures(db, dry_run=False)

    assert [s.name for s in db.scalars(select(Scenario)).all()] == ["BOS — Contend now"]
    assert [t.name for t in db.scalars(select(TradeProposal)).all()] == ["Tatum for Brown swap"]
    assert [c.name for c in db.scalars(select(ComparisonSet)).all()] == ["Deadline shortlist"]
    # A deleted proposal takes its join rows with it.
    assert db.scalars(select(TradeTeam)).all() == []


def test_a_clean_database_reports_nothing(db: Session, seeded_league: dict) -> None:
    assert find_fixture_entities(db) == {"scenarios": [], "trades": [], "comparisons": []}


def test_the_demo_seed_leaves_no_test_entities(db: Session) -> None:
    """The database CI runs the end-to-end suite against starts clean of them."""
    from app.ingestion.demo_seed import seed_demo

    seed_demo(db, seasons=("2025-26",))
    assert find_fixture_entities(db) == {"scenarios": [], "trades": [], "comparisons": []}


def test_comparisons_are_repaired_not_left_dangling(db: Session, seeded_league: dict) -> None:
    """Comparison sets store trade ids as a JSON list, so deleting a proposal can leave a
    set pointing at nothing — and the whole comparison would then 404."""
    team_id = seeded_league["team_a"].id
    automated = TradeProposal(name="E2E RosterLab deal")
    keeper_a = TradeProposal(name="Tatum for Brown swap")
    keeper_b = TradeProposal(name="Deadline plan B")
    db.add_all([automated, keeper_a, keeper_b])
    db.flush()
    db.add(TradeTeam(trade_id=automated.id, team_id=team_id))
    # One set survives with two live trades; one is left uncomparable and goes.
    survives = ComparisonSet(name="Board", trade_ids=[automated.id, keeper_a.id, keeper_b.id])
    uncomparable = ComparisonSet(name="Pair", trade_ids=[automated.id, keeper_a.id])
    db.add_all([survives, uncomparable])
    db.commit()

    summary = purge_fixtures(db, dry_run=False)
    assert summary["repaired_comparisons"] == {"pruned": 1, "deleted": 1}

    remaining = db.scalars(select(ComparisonSet)).all()
    assert [c.name for c in remaining] == ["Board"]
    assert automated.id not in remaining[0].trade_ids
    assert len(remaining[0].trade_ids) == 2
