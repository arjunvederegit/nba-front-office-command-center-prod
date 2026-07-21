"""Shared test fixtures.

All NBA-like records created here are SYNTHETIC TEST FIXTURES for deterministic
tests only — they are never loaded by production configuration (see §2.11 of the
product spec and data/README.md)."""

import os
import tempfile
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.db.models import (  # noqa: E402
    Base,
    Contract,
    ContractYear,
    LeagueCapParameters,
    Player,
    RosterEntry,
    Team,
)


@pytest.fixture()
def db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # one shared connection: TestClient threads see the schema
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    session = TestSession()
    yield session
    session.close()


@pytest.fixture()
def cap_params(db: Session) -> LeagueCapParameters:
    params = LeagueCapParameters(
        league_year="2026-27",
        salary_cap=164_961_000,
        luxury_tax=200_428_000,
        first_apron=209_015_000,
        second_apron=221_686_000,
        minimum_team_salary=148_465_000,
        source_name="test fixture (values match official 2026-27 release)",
    )
    db.add(params)
    db.commit()
    return params


def make_team(db: Session, nba_id: int, abbr: str, name: str | None = None) -> Team:
    team = Team(
        nba_team_id=nba_id,
        full_name=name or f"Test {abbr}",
        abbreviation=abbr,
        nickname=abbr,
        city="Testville",
    )
    db.add(team)
    db.commit()
    return team


def make_player(
    db: Session,
    nba_id: int,
    name: str,
    team: Team | None = None,
    season: str = "2025-26",
    salary: int | None = None,
    league_year: str = "2026-27",
    contract_type: str = "standard",
    signed_date: date | None = None,
    no_trade_clause: bool | None = None,
    birth_date: date | None = date(1998, 1, 1),
) -> Player:
    player = Player(
        nba_player_id=nba_id,
        full_name=name,
        is_active=True,
        birth_date=birth_date,
        height_inches=78,
        position="F",
    )
    db.add(player)
    db.flush()
    if team is not None:
        db.add(
            RosterEntry(
                team_id=team.id,
                player_id=player.id,
                season=season,
                is_current=True,
                age=27.0,
                source_retrieved_at=datetime.now(UTC),
            )
        )
    if salary is not None:
        contract = Contract(
            player_id=player.id,
            contract_type=contract_type,
            signed_date=signed_date,
            no_trade_clause=no_trade_clause,
            source_name="test fixture",
            source_date=date(2026, 7, 1),
        )
        db.add(contract)
        db.flush()
        db.add(ContractYear(contract_id=contract.id, season=league_year, salary=salary))
    db.commit()
    return player


@pytest.fixture()
def two_teams(db: Session) -> tuple[Team, Team]:
    return make_team(db, 1, "AAA"), make_team(db, 2, "BBB")


@pytest.fixture()
def tmp_sqlite_url() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield f"sqlite:///{path}"
    os.unlink(path)
