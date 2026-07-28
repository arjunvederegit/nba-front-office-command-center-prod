"""Resolving an external contract record to a player in this database.

Measured on the live database (5,121 players, 530 rostered for 2025-26):

- **38 lowercase names are duplicated.** `Brandon Williams` exists twice — nba_player_id
  1585, not on any roster, and 1630314, who is. The old join built
  `{full_name.lower(): p}` over every player with no disambiguation, so a coin flip
  (whichever row the database returned last) decided which one got the contract, and the
  losing team's payroll was `None` forever.
- **26 names carry diacritics, and the database is internally inconsistent about them.**
  `Bogdan Bogdanović` keeps them; `Alperen Sengun` does not. A blanket normalize would
  therefore break as many matches as it fixes, which is why unaccenting is a **fallback
  tier**, tried only after the exact name fails.
- **Unaccenting introduces no new collisions** — 38 duplicate names before, 38 after — so
  the tier is safe to add.

Nothing is ever fuzzy-matched. A record that cannot be resolved to exactly one player is
reported, not guessed at.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Player, RosterEntry

SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v"}


def unaccent(value: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c)
    )


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", value.lower()).strip()


def strip_suffix(value: str) -> str:
    parts = value.split()
    while len(parts) > 2 and parts[-1].lower().strip(".") in {s.strip(".") for s in SUFFIXES}:
        parts = parts[:-1]
    return " ".join(parts)


@dataclass
class Resolution:
    player: Player | None
    method: str  # nba_player_id | exact_name | unaccented | suffix_insensitive | none
    ambiguous_candidates: list[Player] = field(default_factory=list)

    @property
    def resolved(self) -> bool:
        return self.player is not None


class PlayerIdentityIndex:
    """Tiered lookup built once per import.

    Tiers are tried in descending confidence and **never** fall through silently: the
    method that produced a match is recorded on every resolution, and an ambiguity is
    returned as an ambiguity rather than resolved by picking.
    """

    def __init__(self, db: Session, season: str):
        self._players = list(db.scalars(select(Player)).all())
        self._rostered: set[str] = {
            entry.player_id
            for entry in db.scalars(
                select(RosterEntry).where(
                    RosterEntry.season == season, RosterEntry.is_current
                )
            ).all()
        }
        self._by_nba_id: dict[int, Player] = {
            p.nba_player_id: p for p in self._players if p.nba_player_id is not None
        }
        self._by_exact: dict[str, list[Player]] = defaultdict(list)
        self._by_unaccented: dict[str, list[Player]] = defaultdict(list)
        self._by_stripped: dict[str, list[Player]] = defaultdict(list)
        for player in self._players:
            name = player.full_name or ""
            self._by_exact[_normalize(name)].append(player)
            self._by_unaccented[_normalize(unaccent(name))].append(player)
            self._by_stripped[_normalize(unaccent(strip_suffix(name)))].append(player)

    @property
    def rostered_player_ids(self) -> set[str]:
        return self._rostered

    def _disambiguate(self, candidates: list[Player], method: str) -> Resolution:
        if len(candidates) == 1:
            return Resolution(candidates[0], method)
        # A currently-rostered player is the one a contract snapshot is about; a
        # historical namesake is not. This resolves `Brandon Williams` deterministically.
        on_roster = [p for p in candidates if p.id in self._rostered]
        if len(on_roster) == 1:
            return Resolution(on_roster[0], f"{method}+roster")
        return Resolution(None, "ambiguous", ambiguous_candidates=candidates)

    def resolve(self, *, nba_player_id: int | None, name: str) -> Resolution:
        if nba_player_id is not None:
            player = self._by_nba_id.get(nba_player_id)
            if player is not None:
                return Resolution(player, "nba_player_id")
        for index, method in (
            (self._by_exact, "exact_name"),
            (self._by_unaccented, "unaccented"),
            (self._by_stripped, "suffix_insensitive"),
        ):
            key = {
                "exact_name": _normalize(name),
                "unaccented": _normalize(unaccent(name)),
                "suffix_insensitive": _normalize(unaccent(strip_suffix(name))),
            }[method]
            candidates = index.get(key, [])
            if candidates:
                resolution = self._disambiguate(candidates, method)
                # An ambiguity at a high-confidence tier is reported rather than
                # retried at a looser one, which would only widen the candidate set.
                return resolution
        return Resolution(None, "none")
