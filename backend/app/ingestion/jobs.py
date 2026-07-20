"""Idempotent ingestion jobs.

Every job upserts on natural keys, so re-running after a partial failure is safe and a
failed endpoint never destroys the last valid snapshot. All NBA.com access goes through
SwarNBAApiProvider — jobs never import nba_api directly."""

import asyncio
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.cache import get_cache
from app.core.logging import get_logger
from app.db.models import (
    Contract,
    ContractYear,
    Game,
    Player,
    PlayerSeasonStats,
    PlayerTeamHistory,
    RosterEntry,
    Standing,
    Team,
    TeamSeasonStats,
)
from app.ingestion.runs import sync_run
from app.integrations.contracts import get_contract_provider
from app.integrations.nba_api.provider import SwarNBAApiProvider, get_provider

logger = get_logger(__name__)


def _team_map(db: Session) -> dict[int, Team]:
    return {t.nba_team_id: t for t in db.scalars(select(Team)).all()}


def _player_map(db: Session) -> dict[int, Player]:
    return {p.nba_player_id: p for p in db.scalars(select(Player)).all()}


def _apply(entity: Any, values: dict[str, Any]) -> None:
    for key, value in values.items():
        setattr(entity, key, value)


def sync_teams(db: Session, provider: SwarNBAApiProvider | None = None) -> int:
    provider = provider or get_provider()
    with sync_run(db, "sync_teams") as run:
        records = asyncio.run(provider.fetch_teams())
        existing = _team_map(db)
        now = datetime.now(UTC)
        for record in records:
            values = {**record, "source_retrieved_at": now, "ingestion_run_id": run.id}
            team = existing.get(record["nba_team_id"])
            if team is None:
                db.add(Team(**values))
            else:
                _apply(team, values)
            run.rows_written += 1
        db.commit()
        return run.rows_written


def sync_players(db: Session, provider: SwarNBAApiProvider | None = None) -> int:
    provider = provider or get_provider()
    with sync_run(db, "sync_players") as run:
        records = asyncio.run(provider.fetch_players())
        existing = _player_map(db)
        now = datetime.now(UTC)
        for record in records:
            values = {**record, "source_retrieved_at": now, "ingestion_run_id": run.id}
            player = existing.get(record["nba_player_id"])
            if player is None:
                db.add(Player(**values))
            else:
                _apply(player, values)
            run.rows_written += 1
        db.commit()
        return run.rows_written


def sync_rosters(db: Session, season: str | None = None, provider=None) -> int:
    """Fetch all 30 rosters, supersede the previous snapshot, and enrich player bio
    fields (height/weight/position/experience/birth date) from roster rows."""
    settings = get_settings()
    season = season or settings.current_season
    provider = provider or get_provider()
    with sync_run(db, "sync_rosters") as run:
        rows = asyncio.run(provider.fetch_rosters(season))
        teams = _team_map(db)
        players = _player_map(db)
        now = datetime.now(UTC)

        current = db.scalars(
            select(RosterEntry).where(RosterEntry.season == season, RosterEntry.is_current)
        ).all()
        for entry in current:
            entry.is_current = False
            entry.valid_to = now

        for row in rows:
            team = teams.get(row["nba_team_id"])
            player = players.get(row["nba_player_id"])
            if team is None:
                continue
            if player is None:
                # Player appears on an NBA.com roster but not in static data (e.g. new
                # signing): create the identity record from the roster row itself.
                player = Player(
                    nba_player_id=row["nba_player_id"],
                    full_name=row.get("player_name") or f"NBA Player {row['nba_player_id']}",
                    is_active=True,
                    source_record_id=str(row["nba_player_id"]),
                    source_retrieved_at=now,
                    ingestion_run_id=run.id,
                )
                db.add(player)
                db.flush()
                players[row["nba_player_id"]] = player
            for field in ("position", "birth_date", "height_inches", "weight_lbs", "years_experience"):
                if row.get(field) is not None:
                    setattr(player, field, row[field])
            db.add(
                RosterEntry(
                    team_id=team.id,
                    player_id=player.id,
                    season=season,
                    jersey_number=row.get("jersey_number"),
                    position=row.get("position"),
                    age=row.get("age"),
                    is_current=True,
                    source_record_id=row.get("source_record_id"),
                    source_retrieved_at=row.get("source_retrieved_at") or now,
                    valid_from=now,
                    ingestion_run_id=run.id,
                )
            )
            db.add(
                PlayerTeamHistory(
                    player_id=player.id,
                    team_id=team.id,
                    season=season,
                    observed_at=now,
                    source_record_id=row.get("source_record_id"),
                    source_retrieved_at=row.get("source_retrieved_at") or now,
                    ingestion_run_id=run.id,
                )
            )
            run.rows_written += 1
        db.commit()
        return run.rows_written


def sync_standings(db: Session, season: str | None = None, provider=None) -> int:
    settings = get_settings()
    season = season or settings.current_season
    provider = provider or get_provider()
    with sync_run(db, "sync_standings") as run:
        rows = asyncio.run(provider.fetch_standings(season))
        teams = _team_map(db)
        for row in rows:
            team = teams.get(row["nba_team_id"])
            if team is None:
                continue
            team.conference = row.get("conference")
            team.division = row.get("division")
            values = {
                "team_id": team.id,
                "season": season,
                "wins": row["wins"],
                "losses": row["losses"],
                "win_pct": row["win_pct"],
                "conference": row.get("conference"),
                "conference_rank": row.get("conference_rank"),
                "playoff_rank": row.get("playoff_rank"),
                "details": row.get("details", {}),
                "source_record_id": row.get("source_record_id"),
                "source_retrieved_at": row.get("source_retrieved_at"),
                "ingestion_run_id": run.id,
            }
            standing = db.scalar(
                select(Standing).where(Standing.team_id == team.id, Standing.season == season)
            )
            if standing is None:
                db.add(Standing(**values))
            else:
                _apply(standing, values)
            run.rows_written += 1
        db.commit()
        return run.rows_written


def sync_player_stats(db: Session, seasons: list[str] | None = None, provider=None) -> int:
    settings = get_settings()
    seasons = seasons or settings.history_season_list
    provider = provider or get_provider()
    with sync_run(db, "sync_player_stats") as run:
        players = _player_map(db)
        teams = _team_map(db)
        for season in seasons:
            rows = asyncio.run(provider.fetch_player_stats(season))
            try:
                rows += asyncio.run(provider.fetch_player_estimated_metrics(season))
            except Exception as exc:
                # Estimated metrics are optional enrichment with a documented fallback;
                # base+advanced remain authoritative.
                logger.warning("estimated metrics unavailable for %s: %s", season, exc)
            for row in rows:
                player = players.get(row["nba_player_id"])
                if player is None:
                    continue
                team = teams.get(row.get("nba_team_id") or -1)
                values = {
                    "player_id": player.id,
                    "team_id": team.id if team else None,
                    "season": season,
                    "stat_type": row["stat_type"],
                    "games_played": row.get("games_played"),
                    "minutes": row.get("minutes"),
                    "stats": row.get("stats", {}),
                    "source_record_id": row.get("source_record_id"),
                    "source_retrieved_at": row.get("source_retrieved_at"),
                    "ingestion_run_id": run.id,
                }
                stat = db.scalar(
                    select(PlayerSeasonStats).where(
                        PlayerSeasonStats.player_id == player.id,
                        PlayerSeasonStats.season == season,
                        PlayerSeasonStats.stat_type == row["stat_type"],
                    )
                )
                if stat is None:
                    db.add(PlayerSeasonStats(**values))
                else:
                    _apply(stat, values)
                run.rows_written += 1
            db.commit()
        return run.rows_written


def sync_team_stats(db: Session, seasons: list[str] | None = None, provider=None) -> int:
    settings = get_settings()
    seasons = seasons or settings.history_season_list
    provider = provider or get_provider()
    with sync_run(db, "sync_team_stats") as run:
        teams = _team_map(db)
        for season in seasons:
            rows = asyncio.run(provider.fetch_team_stats(season))
            for row in rows:
                team = teams.get(row["nba_team_id"])
                if team is None:
                    continue
                values = {
                    "team_id": team.id,
                    "season": season,
                    "stat_type": row["stat_type"],
                    "stats": row.get("stats", {}),
                    "source_record_id": row.get("source_record_id"),
                    "source_retrieved_at": row.get("source_retrieved_at"),
                    "ingestion_run_id": run.id,
                }
                stat = db.scalar(
                    select(TeamSeasonStats).where(
                        TeamSeasonStats.team_id == team.id,
                        TeamSeasonStats.season == season,
                        TeamSeasonStats.stat_type == row["stat_type"],
                    )
                )
                if stat is None:
                    db.add(TeamSeasonStats(**values))
                else:
                    _apply(stat, values)
                run.rows_written += 1
            db.commit()
        return run.rows_written


def sync_games(db: Session, season: str | None = None, provider=None) -> int:
    settings = get_settings()
    season = season or settings.current_season
    provider = provider or get_provider()
    with sync_run(db, "sync_games") as run:
        rows = asyncio.run(provider.fetch_games(season))
        teams = _team_map(db)
        for row in rows:
            home = teams.get(row.get("home_nba_team_id") or -1)
            away = teams.get(row.get("away_nba_team_id") or -1)
            values = {
                "nba_game_id": row["nba_game_id"],
                "season": season,
                "game_date": row["game_date"],
                "home_team_id": home.id if home else None,
                "away_team_id": away.id if away else None,
                "home_score": row.get("home_score"),
                "away_score": row.get("away_score"),
                "status": row.get("status", "final"),
                "source_record_id": row.get("source_record_id"),
                "source_retrieved_at": row.get("source_retrieved_at"),
                "ingestion_run_id": run.id,
            }
            game = db.scalar(select(Game).where(Game.nba_game_id == row["nba_game_id"]))
            if game is None:
                db.add(Game(**values))
            else:
                _apply(game, values)
            run.rows_written += 1
        db.commit()
        return run.rows_written


def sync_contracts(db: Session) -> int:
    """Ingest contracts from the configured secondary provider. With no provider this
    records an explicit no-op run — salary features stay honestly unavailable."""
    contract_provider = get_contract_provider()
    with sync_run(db, "sync_contracts") as run:
        if contract_provider is None:
            run.detail = {"provider": None, "note": "no contract provider configured"}
            db.commit()
            return 0
        records = contract_provider.fetch_contracts()
        players = {p.full_name.lower(): p for p in db.scalars(select(Player)).all()}
        players_by_nba_id = _player_map(db)
        now = datetime.now(UTC)
        matched = 0
        unmatched: list[str] = []
        for record in records:
            player = None
            if record.nba_player_id is not None:
                player = players_by_nba_id.get(record.nba_player_id)
            if player is None:
                player = players.get(record.player_name.lower())
            if player is None:
                unmatched.append(record.player_name)
                continue
            contract = db.scalar(select(Contract).where(Contract.player_id == player.id))
            if contract is None:
                contract = Contract(
                    player_id=player.id,
                    contract_type=record.contract_type,
                    signed_date=record.signed_date,
                    no_trade_clause=record.no_trade_clause,
                    source_provider=contract_provider.name,
                    source_name=record.source_name,
                    source_date=record.source_date,
                    source_retrieved_at=now,
                    ingestion_run_id=run.id,
                )
                db.add(contract)
                db.flush()
            else:
                contract.contract_type = record.contract_type
                contract.signed_date = record.signed_date
                contract.no_trade_clause = record.no_trade_clause
                contract.source_name = record.source_name
                contract.source_date = record.source_date
                contract.source_retrieved_at = now
            year = db.scalar(
                select(ContractYear).where(
                    ContractYear.contract_id == contract.id,
                    ContractYear.season == record.season,
                )
            )
            values = {
                "contract_id": contract.id,
                "season": record.season,
                "salary": record.salary,
                "guaranteed": record.guaranteed,
                "player_option": record.player_option,
                "team_option": record.team_option,
                "source_provider": contract_provider.name,
                "source_retrieved_at": now,
                "ingestion_run_id": run.id,
            }
            if year is None:
                db.add(ContractYear(**values))
            else:
                _apply(year, values)
            matched += 1
        run.rows_written = matched
        run.detail = {
            "provider": contract_provider.name,
            "matched": matched,
            "unmatched_players": unmatched[:50],
            "rejected_rows": getattr(contract_provider, "rejected_rows", [])[:50],
        }
        db.commit()
        return matched


def sync_all(db: Session) -> dict[str, Any]:
    """Full refresh in dependency order. Individual failures are recorded and do not
    abort later jobs — the last valid snapshot always survives."""
    results: dict[str, Any] = {}
    steps = [
        ("sync_teams", lambda: sync_teams(db)),
        ("sync_players", lambda: sync_players(db)),
        ("sync_rosters", lambda: sync_rosters(db)),
        ("sync_standings", lambda: sync_standings(db)),
        ("sync_team_stats", lambda: sync_team_stats(db)),
        ("sync_player_stats", lambda: sync_player_stats(db)),
        ("sync_games", lambda: sync_games(db)),
        ("sync_contracts", lambda: sync_contracts(db)),
    ]
    for name, step in steps:
        try:
            results[name] = {"status": "succeeded", "rows": step()}
        except Exception as exc:  # noqa: BLE001 — recorded, surfaced via /data-health
            results[name] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    from app.ingestion.quality import validate_data

    results["validate_data"] = {"status": "succeeded", "issues": validate_data(db)}
    get_cache().bump_data_version()
    return results
