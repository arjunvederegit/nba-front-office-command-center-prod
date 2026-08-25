"""Deterministic demo database for CI and local end-to-end runs.

**This is not NBA data and must never be presented as NBA data.**

Why it exists: the Playwright suite exercises the full decision flow, and CI has no
ingested database. Without a seed, the end-to-end gate cannot run at all — which is how
the flow behind QA-1…QA-13 came to be unguarded.

What is real and what is not:

- **Team identity is real and provider-backed.** It comes from `nba_api`'s *bundled
  static* team table (offline, no network, no scraping) — the same provider the app
  already uses. Rows are stamped ``source_provider="nba_api_static"``.
- **Everything else is synthetic and labelled as such.** Players are named
  ``Demo <Team> <n>``; every synthetic row is stamped ``source_provider="demo_seed"``
  and carries ``valid_from`` at seed time. No synthetic value is ever attributed to
  NBA.com.

Safety: `seed_demo` refuses to run against a database that already holds `nba_api`
rows, so it cannot contaminate a real development database. Point it at a dedicated
``DATABASE_URL`` (see `make seed-demo` and `playwright.config.ts`).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import (
    DataSyncRun,
    Player,
    PlayerSeasonStats,
    RosterEntry,
    Standing,
    Team,
    TeamSeasonStats,
)

DEMO_PROVIDER = "demo_seed"
STATIC_PROVIDER = "nba_api_static"
PLAYERS_PER_TEAM = 15


class DemoSeedRefused(RuntimeError):
    """Raised when the target database holds real provider data."""


def _has_real_provider_rows(db: Session) -> bool:
    for model in (Team, Player, PlayerSeasonStats, RosterEntry):
        count = db.scalar(
            select(func.count()).select_from(model).where(model.source_provider == "nba_api")
        )
        if count:
            return True
    return False


def _base_stats(seed: int) -> dict:
    minutes = 9.0 + (seed % 13) * 2.1
    return {
        "PTS": 3.5 + (seed % 17) * 1.35,
        "REB": 1.6 + (seed % 11) * 0.72,
        "AST": 0.7 + (seed % 9) * 0.78,
        "STL": 0.2 + (seed % 7) * 0.19,
        "BLK": 0.1 + (seed % 6) * 0.26,
        "TOV": 0.5 + (seed % 8) * 0.21,
        "FGA": 3.2 + (seed % 15) * 1.15,
        "FG3A": 0.4 + (seed % 12) * 0.72,
        "FTA": 0.6 + (seed % 9) * 0.55,
        "PLUS_MINUS": -5.0 + (seed % 19) * 0.6,
        "AGE": 20.0 + (seed % 16),
        "MIN": minutes,
    }


def _advanced_stats(seed: int) -> dict:
    return {
        "OFF_RATING": 106.0 + (seed % 17) * 0.95,
        "DEF_RATING": 105.0 + (seed % 15) * 1.05,
        "NET_RATING": -8.0 + (seed % 21) * 0.8,
        "AST_PCT": 0.05 + (seed % 18) * 0.017,
        "AST_TO": 0.7 + (seed % 11) * 0.19,
        "OREB_PCT": 0.008 + (seed % 13) * 0.0095,
        "DREB_PCT": 0.05 + (seed % 16) * 0.0125,
        "REB_PCT": 0.03 + (seed % 14) * 0.011,
        "TM_TOV_PCT": 0.06 + (seed % 12) * 0.0095,
        "EFG_PCT": 0.44 + (seed % 15) * 0.0095,
        "TS_PCT": 0.47 + (seed % 17) * 0.0092,
        "USG_PCT": 0.09 + (seed % 19) * 0.0105,
        "PACE": 96.0 + (seed % 7) * 1.1,
        "PIE": 0.02 + (seed % 16) * 0.0085,
    }


def seed_demo(db: Session, *, seasons: tuple[str, ...] | None = None) -> dict:
    """Populate a database with the demo league. Idempotent for a given target."""
    settings = get_settings()
    if _has_real_provider_rows(db):
        raise DemoSeedRefused(
            "target database already holds nba_api rows; refusing to mix demo data with "
            "real provider data. Point DATABASE_URL at a dedicated demo database."
        )
    if db.scalar(select(func.count()).select_from(Team)):
        return {"skipped": "database already seeded", "teams": 0}

    from nba_api.stats.static import teams as static_teams

    season_list = seasons or tuple(settings.history_season_list[-2:])
    now = datetime.now(UTC)
    retrieved_at = now - timedelta(hours=3)

    run = DataSyncRun(
        job_name="seed_demo",
        status="running",
        started_at=now,
        detail={"note": "synthetic demo league; not NBA.com data"},
    )
    db.add(run)
    db.flush()

    team_rows: list[Team] = []
    for raw in static_teams.get_teams():
        team = Team(
            nba_team_id=int(raw["id"]),
            full_name=raw["full_name"],
            abbreviation=raw["abbreviation"],
            nickname=raw["nickname"],
            city=raw["city"],
            state=raw.get("state"),
            year_founded=raw.get("year_founded"),
            conference="East" if raw["abbreviation"] in _EAST else "West",
            source_provider=STATIC_PROVIDER,
            source_record_id=str(raw["id"]),
            source_retrieved_at=retrieved_at,
            valid_from=retrieved_at,
            ingestion_run_id=run.id,
        )
        db.add(team)
        team_rows.append(team)
    db.flush()

    players_written = 0
    for team_index, team in enumerate(sorted(team_rows, key=lambda t: t.abbreviation)):
        wins = 22 + (team_index * 13) % 40
        db.add(
            Standing(
                team_id=team.id,
                season=settings.current_season,
                wins=wins,
                losses=82 - wins,
                win_pct=round(wins / 82, 3),
                conference=team.conference,
                conference_rank=1 + team_index % 15,
                source_provider=DEMO_PROVIDER,
                source_retrieved_at=retrieved_at,
                valid_from=retrieved_at,
                ingestion_run_id=run.id,
            )
        )
        off = 108.0 + (team_index % 11) * 0.9
        deff = 108.0 + ((team_index + 5) % 11) * 0.9
        db.add(
            TeamSeasonStats(
                team_id=team.id,
                season=settings.current_season,
                stat_type="advanced",
                stats={
                    "OFF_RATING": off,
                    "DEF_RATING": deff,
                    "NET_RATING": round(off - deff, 2),
                    "AST_PCT": 0.58 + (team_index % 9) * 0.008,
                    "DREB_PCT": 0.70 + (team_index % 8) * 0.006,
                    "TM_TOV_PCT": 0.12 + (team_index % 7) * 0.004,
                    "TS_PCT": 0.55 + (team_index % 10) * 0.004,
                    "PACE": 97.5 + (team_index % 6) * 0.7,
                },
                source_provider=DEMO_PROVIDER,
                source_retrieved_at=retrieved_at,
                valid_from=retrieved_at,
                ingestion_run_id=run.id,
            )
        )
        db.add(
            TeamSeasonStats(
                team_id=team.id,
                season=settings.current_season,
                stat_type="base",
                stats={
                    "PTS": 108.0 + (team_index % 12) * 1.1,
                    "FG3A": 30.0 + (team_index % 14) * 0.9,
                    "STL": 6.5 + (team_index % 9) * 0.25,
                    "BLK": 4.0 + (team_index % 8) * 0.28,
                    "REB": 42.0 + (team_index % 7) * 0.8,
                    "AST": 24.0 + (team_index % 10) * 0.7,
                },
                source_provider=DEMO_PROVIDER,
                source_retrieved_at=retrieved_at,
                valid_from=retrieved_at,
                ingestion_run_id=run.id,
            )
        )

        for slot in range(PLAYERS_PER_TEAM):
            seed = team_index * PLAYERS_PER_TEAM + slot
            player = Player(
                nba_player_id=9_000_000 + seed,
                full_name=f"Demo {team.abbreviation} {slot + 1:02d}",
                first_name="Demo",
                last_name=f"{team.abbreviation}{slot + 1:02d}",
                is_active=True,
                birth_date=date(2005 - (seed % 16), 1 + (seed % 12), 1 + (seed % 28)),
                height_inches=72 + (seed % 12),
                weight_lbs=180 + (seed % 60),
                position=("G", "G", "F", "F", "C")[slot % 5],
                years_experience=seed % 14,
                source_provider=DEMO_PROVIDER,
                source_retrieved_at=retrieved_at,
                valid_from=retrieved_at,
                ingestion_run_id=run.id,
            )
            db.add(player)
            db.flush()
            players_written += 1

            db.add(
                RosterEntry(
                    team_id=team.id,
                    player_id=player.id,
                    season=settings.current_season,
                    jersey_number=str(slot + 1),
                    position=player.position,
                    age=float(20 + (seed % 16)),
                    is_current=True,
                    source_provider=DEMO_PROVIDER,
                    source_retrieved_at=retrieved_at,
                    valid_from=retrieved_at,
                    ingestion_run_id=run.id,
                )
            )
            for season_index, season in enumerate(season_list):
                seed_s = seed + season_index * 7
                base = _base_stats(seed_s)
                minutes = float(base.pop("MIN"))
                games = 48 + (seed_s % 9) * 4
                advanced = _advanced_stats(seed_s)
                possessions = games * minutes * 2.1
                db.add(
                    PlayerSeasonStats(
                        player_id=player.id,
                        team_id=team.id,
                        season=season,
                        stat_type="base",
                        games_played=games,
                        minutes=minutes,
                        stats={**base, "POSS": possessions},
                        source_provider=DEMO_PROVIDER,
                        source_retrieved_at=retrieved_at,
                        valid_from=retrieved_at,
                        ingestion_run_id=run.id,
                    )
                )
                db.add(
                    PlayerSeasonStats(
                        player_id=player.id,
                        team_id=team.id,
                        season=season,
                        stat_type="advanced",
                        games_played=games,
                        minutes=minutes,
                        stats={**advanced, "POSS": possessions},
                        source_provider=DEMO_PROVIDER,
                        source_retrieved_at=retrieved_at,
                        valid_from=retrieved_at,
                        ingestion_run_id=run.id,
                    )
                )
            # Season-totals rows so Player Explorer's "season totals" view has content.
            totals_games = 48 + (seed % 9) * 4
            totals_minutes = 9.0 + (seed % 13) * 2.1
            db.add(
                PlayerSeasonStats(
                    player_id=player.id,
                    team_id=team.id,
                    season=settings.current_season,
                    stat_type="csv_totals",
                    games_played=totals_games,
                    minutes=round(totals_minutes * totals_games, 1),
                    stats={
                        "totals": {
                            "PTS": round((3.5 + (seed % 17) * 1.35) * totals_games),
                            "REB": round((1.6 + (seed % 11) * 0.72) * totals_games),
                            "AST": round((0.7 + (seed % 9) * 0.78) * totals_games),
                            "FGA": round((3.2 + (seed % 15) * 1.15) * totals_games),
                            "FG3A": round((0.4 + (seed % 12) * 0.72) * totals_games),
                        },
                        "per_game": {
                            "PTS": round(3.5 + (seed % 17) * 1.35, 2),
                            "REB": round(1.6 + (seed % 11) * 0.72, 2),
                            "AST": round(0.7 + (seed % 9) * 0.78, 2),
                        },
                        "rates": {
                            "FG_PCT": round(0.42 + (seed % 13) * 0.008, 3),
                            "FG3_PCT": round(0.30 + (seed % 15) * 0.008, 3),
                            "FT_PCT": round(0.68 + (seed % 11) * 0.015, 3),
                        },
                        "source": "demo_seed (synthetic)",
                    },
                    source_provider=DEMO_PROVIDER,
                    source_retrieved_at=retrieved_at,
                    valid_from=retrieved_at,
                    ingestion_run_id=run.id,
                )
            )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.rows_written = players_written
    db.commit()
    return {
        "teams": len(team_rows),
        "players": players_written,
        "seasons": list(season_list),
        "provider": DEMO_PROVIDER,
        "note": "synthetic demo league — never NBA.com data",
    }


_EAST = {
    "ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DET", "IND",
    "MIA", "MIL", "NYK", "ORL", "PHI", "TOR", "WAS",
}  # fmt: skip
