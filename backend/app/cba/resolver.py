"""Request-scoped batching for the salary lookups behind every trade evaluation.

Measured on the live database with `contracts` at **0 rows** — the cheapest possible
case, because a missing contract is one query that returns nothing:

    POST /trades/evaluate  (2-for-2)        61 queries
    POST /trades/generate  (focal BOS)   21,326 queries in 2.15 s

of which 16,640 were the same `SELECT … FROM contracts WHERE player_id = ?` and 1,169
were `SELECT … FROM league_cap_parameters` for one immutable row. With contract data
loaded the plan measured 47,158 queries / 5.17 s on local SQLite; on the compose
Postgres path that is 7–14 s of pure round-trip latency.

The cache lives in `Session.info`, so its lifetime is exactly the request's session —
`get_db` creates one per request — and it is **cleared on every flush and commit**, so a
write inside a session can never be served a stale read. Nothing here is global.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.db.models import Contract, ContractYear, LeagueCapParameters, Player, RosterEntry

_CACHE_KEY = "rosterlab_resolver_cache"


def _cache(db: Session) -> dict[str, Any]:
    cache = db.info.get(_CACHE_KEY)
    if cache is None:
        cache = {"cap_params": {}, "salary": {}, "payroll": {}, "roster": {}, "player": {}}
        db.info[_CACHE_KEY] = cache
    return cache


def reset(db: Session) -> None:
    db.info.pop(_CACHE_KEY, None)


@event.listens_for(Session, "after_flush")
def _clear_on_flush(session: Session, flush_context: Any) -> None:
    session.info.pop(_CACHE_KEY, None)


@event.listens_for(Session, "after_commit")
def _clear_on_commit(session: Session) -> None:
    session.info.pop(_CACHE_KEY, None)


@event.listens_for(Session, "after_rollback")
def _clear_on_rollback(session: Session) -> None:
    session.info.pop(_CACHE_KEY, None)


# ------------------------------------------------------------------ cap parameters


def cap_params_row(db: Session, league_year: str) -> LeagueCapParameters | None:
    """One immutable row per league year, fetched at most once per session.

    `load_cap_params` was called 1,169 times in a single `/trades/generate` request.
    """
    cache = _cache(db)["cap_params"]
    if league_year not in cache:
        cache[league_year] = db.scalar(
            select(LeagueCapParameters).where(LeagueCapParameters.league_year == league_year)
        )
    return cache[league_year]


# ------------------------------------------------------------------------ salaries


def salaries(
    db: Session, player_ids: list[str], league_year: str
) -> dict[str, tuple[int | None, Contract | None]]:
    """`{player_id: (salary_for_league_year, contract)}` for the ids not already cached.

    One query for the contracts and one for their years, rather than two per player. A
    player with no contract is cached as `(None, None)` so the miss is not re-queried —
    which is the whole cost today, since `contracts` is empty.
    """
    cache = _cache(db)["salary"]
    missing = [pid for pid in dict.fromkeys(player_ids) if (pid, league_year) not in cache]
    if missing:
        contracts = list(
            db.scalars(select(Contract).where(Contract.player_id.in_(missing))).all()
        )
        by_player: dict[str, Contract] = {}
        for contract in contracts:
            # Deterministic when a player somehow has more than one contract row: the
            # per-player lookup it replaces took whichever the database returned first.
            existing = by_player.get(contract.player_id)
            if existing is None or contract.id < existing.id:
                by_player[contract.player_id] = contract

        year_by_contract: dict[str, int] = {}
        if contracts:
            for year in db.scalars(
                select(ContractYear).where(
                    ContractYear.contract_id.in_([c.id for c in contracts]),
                    ContractYear.season == league_year,
                )
            ).all():
                year_by_contract[year.contract_id] = year.salary

        for pid in missing:
            found = by_player.get(pid)
            cache[(pid, league_year)] = (
                (year_by_contract.get(found.id), found) if found is not None else (None, None)
            )

    return {pid: cache[(pid, league_year)] for pid in dict.fromkeys(player_ids)}


def player_salary(
    db: Session, player_id: str, league_year: str
) -> tuple[int | None, Contract | None]:
    return salaries(db, [player_id], league_year)[player_id]


# ------------------------------------------------------------------------- payroll


def team_payroll(
    db: Session, team_id: str, season: str, league_year: str
) -> tuple[int | None, int, int]:
    """(payroll or None, players_with_known_salary, roster_size), memoized per team.

    Payroll is still only reported when *every* rostered player has a known salary —
    that all-or-nothing rule is deliberate (a partial sum understates payroll and
    silently skews apron status) and R2c replaces it with a disclosed-coverage model,
    not with a partial sum.
    """
    cache = _cache(db)["payroll"]
    key = (team_id, season, league_year)
    if key not in cache:
        entries = db.scalars(
            select(RosterEntry).where(
                RosterEntry.team_id == team_id,
                RosterEntry.season == season,
                RosterEntry.is_current,
            )
        ).all()
        resolved = salaries(db, [e.player_id for e in entries], league_year)
        known_salaries = [
            salary for e in entries if (salary := resolved[e.player_id][0]) is not None
        ]
        cache[key] = (
            (sum(known_salaries), len(known_salaries), len(entries))
            if entries and len(known_salaries) == len(entries)
            else (None, len(known_salaries), len(entries))
        )
    return cache[key]


# ------------------------------------------------------------------ roster identity


def current_roster(db: Session, season: str) -> dict[str, set[str]]:
    """`{player_id: {team_id, …}}` over the current-season rosters, fetched once.

    `build_trade_context` re-ran the membership query for every trade it validated —
    409 identical queries inside one `/trades/generate` request, which evaluates 400
    candidate trades against the same rosters.
    """
    cache = _cache(db)["roster"]
    if season not in cache:
        membership: dict[str, set[str]] = {}
        for entry in db.scalars(
            select(RosterEntry).where(
                RosterEntry.season == season, RosterEntry.is_current
            )
        ).all():
            membership.setdefault(entry.player_id, set()).add(entry.team_id)
        cache[season] = membership
    return cache[season]


def players(db: Session, player_ids: list[str]) -> dict[str, Player]:
    """Batched `Player` lookup. `build_trade_context` called `db.get(Player, …)` once per
    move — 769 queries per generate request."""
    cache = _cache(db)["player"]
    missing = [pid for pid in dict.fromkeys(player_ids) if pid not in cache]
    if missing:
        for player in db.scalars(select(Player).where(Player.id.in_(missing))).all():
            cache[player.id] = player
        for pid in missing:
            cache.setdefault(pid, None)
    return {pid: cache[pid] for pid in dict.fromkeys(player_ids) if cache.get(pid) is not None}
