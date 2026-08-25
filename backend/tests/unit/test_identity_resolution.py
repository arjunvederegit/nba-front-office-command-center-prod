"""Tiered player identity resolution for contract imports (R2a).

The old join was `{full_name.lower(): p}` over 5,121 players with no disambiguation.
Measured on the live database: **38 duplicated lowercase names**, and `Brandon Williams`
exists as both nba_player_id 1585 (not on any roster) and 1630314 (rostered) — so a coin
flip decided which one got the contract, and the losing team's payroll was `None`
forever.

26 names carry diacritics and the database is internally inconsistent about them
(`Bogdan Bogdanović` keeps them, `Alperen Sengun` does not), so unaccenting is a
**fallback tier**, never a blanket normalize. It introduces no new collisions: 38
duplicate names before, 38 after.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.db.models import Player, RosterEntry, Team
from app.ingestion.identity import PlayerIdentityIndex, strip_suffix, unaccent


@pytest.fixture()
def league(db: Session) -> dict:
    team = Team(
        nba_team_id=1610612738,
        full_name="Boston Celtics",
        abbreviation="BOS",
        nickname="Celtics",
        city="Boston",
    )
    db.add(team)
    db.flush()

    def player(nba_id: int, name: str, *, rostered: bool) -> Player:
        p = Player(nba_player_id=nba_id, full_name=name, is_active=rostered)
        db.add(p)
        db.flush()
        if rostered:
            db.add(
                RosterEntry(
                    team_id=team.id,
                    player_id=p.id,
                    season="2025-26",
                    is_current=True,
                    source_retrieved_at=datetime.now(UTC),
                )
            )
        return p

    people = {
        # The real collision: a historical namesake and a current player.
        "williams_old": player(1585, "Brandon Williams", rostered=False),
        "williams_new": player(1630314, "Brandon Williams", rostered=True),
        # Diacritics kept in this database…
        "bogdanovic": player(203992, "Bogdan Bogdanović", rostered=True),
        # …and stripped in this one. Both spellings appear in real snapshots.
        "sengun": player(1630578, "Alperen Sengun", rostered=True),
        "porter": player(1629008, "Michael Porter Jr.", rostered=True),
        # Two historical namesakes, neither rostered: genuinely unresolvable.
        "davis_a": player(76000, "Johnny Davis", rostered=False),
        "davis_b": player(1631098, "Johnny Davis", rostered=False),
    }
    db.commit()
    return {"team": team, **people}


def index(db: Session) -> PlayerIdentityIndex:
    return PlayerIdentityIndex(db, "2025-26")


def test_nba_player_id_wins_over_everything(db: Session, league: dict) -> None:
    """The file provider accepts `nba_player_id`, which is exact identity."""
    result = index(db).resolve(nba_player_id=1585, name="Completely Different Name")
    assert result.player is league["williams_old"]
    assert result.method == "nba_player_id"


def test_a_duplicate_name_resolves_to_the_rostered_player(db: Session, league: dict) -> None:
    """A contract snapshot is about current players; a historical namesake is not."""
    result = index(db).resolve(nba_player_id=None, name="Brandon Williams")
    assert result.player is league["williams_new"]
    assert result.method == "exact_name+roster"


def test_a_genuinely_ambiguous_name_is_refused_not_guessed(db: Session, league: dict) -> None:
    """Two historical namesakes, neither rostered. A wrong binding puts one team's
    salary on another team's books, so no binding is made."""
    result = index(db).resolve(nba_player_id=None, name="Johnny Davis")
    assert result.player is None
    assert result.method == "ambiguous"
    assert len(result.ambiguous_candidates) == 2


def test_diacritics_are_a_fallback_tier_not_a_blanket_normalize(db: Session, league: dict) -> None:
    resolver = index(db)
    # Stored with diacritics, snapshot has them: exact.
    assert resolver.resolve(nba_player_id=None, name="Bogdan Bogdanović").method == "exact_name"
    # Stored with diacritics, snapshot without: the fallback earns the match.
    stripped = resolver.resolve(nba_player_id=None, name="Bogdan Bogdanovic")
    assert stripped.player is league["bogdanovic"]
    assert stripped.method == "unaccented"
    # Stored *without* diacritics, snapshot with: the same tier, in the other direction.
    accented = resolver.resolve(nba_player_id=None, name="Alperen Şengün")
    assert accented.player is league["sengun"]
    assert accented.method == "unaccented"


def test_suffixes_are_matched_insensitively(db: Session, league: dict) -> None:
    result = index(db).resolve(nba_player_id=None, name="Michael Porter")
    assert result.player is league["porter"]
    assert result.method == "suffix_insensitive"


def test_an_unknown_name_resolves_to_nothing(db: Session, league: dict) -> None:
    result = index(db).resolve(nba_player_id=None, name="Nobody At All")
    assert result.player is None
    assert result.method == "none"
    assert result.ambiguous_candidates == []


def test_helpers() -> None:
    assert unaccent("Bogdan Bogdanović") == "Bogdan Bogdanovic"
    assert unaccent("Alperen Şengün") == "Alperen Sengun"
    assert strip_suffix("Michael Porter Jr.") == "Michael Porter"
    assert strip_suffix("Gary Payton II") == "Gary Payton"
    # A two-word name is never shortened, whatever the second word looks like.
    assert strip_suffix("Jaden Ivey") == "Jaden Ivey"
