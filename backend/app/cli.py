"""TradeLab operational CLI.

Usage: python -m app.cli <command>

Commands
  sync-all         Full provider-backed refresh (teams, players, rosters, standings,
                   stats, games, contracts) + data quality validation
  sync-<job>       Run one job (teams|players|rosters|standings|player-stats|team-stats|games|contracts)
  seed-config      Load cap-parameter YAML files into league_cap_parameters
  build-features   Build modeling features from ingested data
  train            Train impact model + archetypes; persist model versions
  score            Score current players, compute availability and team needs
  validate-data    Run data-quality checks
  index-assets     Index local player photos / team logos into the media manifest
  import-stats-csv <path>  Import the user-supplied season-totals CSV (default
                   data/imports/nba_player_stats_2026.csv)
  import-kaggle    Import historical enrichment from the Kaggle basketball dataset
  seed-demo        Populate a DEDICATED database with the synthetic demo league used by
                   the end-to-end suite. Refuses to run where nba_api rows exist.
  contract-coverage
                   Report ROSTER-side contract coverage without importing anything:
                   how many rostered players have a salary for the cap league year,
                   and how many teams therefore have a computable payroll.
  purge-fixtures [--apply]
                   List (or with --apply, delete) scenarios, trade proposals and
                   comparison sets whose names look like automated-test leftovers.
                   Dry run by default.
"""

import json
import sys
from collections.abc import Callable
from datetime import date, datetime

import yaml

from app.config import CAP_RULES_DIR, get_settings
from app.core.logging import configure_logging, get_logger
from app.db.base import SessionLocal

logger = get_logger(__name__)


def seed_config() -> None:
    from sqlalchemy import select

    from app.db.models import LeagueCapParameters

    with SessionLocal() as db:
        for path in sorted(CAP_RULES_DIR.glob("*.yaml")):
            doc = yaml.safe_load(path.read_text())
            params = doc["parameters"]
            values = {
                "league_year": doc["league_year"],
                "salary_cap": params["salary_cap"],
                "luxury_tax": params["luxury_tax"],
                "first_apron": params["first_apron"],
                "second_apron": params["second_apron"],
                "minimum_team_salary": params["minimum_team_salary"],
                "effective_date": date.fromisoformat(str(doc["effective_date"])),
                "source_name": doc["source_name"],
                "source_url": doc.get("source_url"),
                "verified_at": datetime.fromisoformat(str(doc["verified_at"])),
                "notes": doc.get("notes"),
                "extras": doc.get("extras", {}),
            }
            row = db.scalar(
                select(LeagueCapParameters).where(
                    LeagueCapParameters.league_year == doc["league_year"]
                )
            )
            if row is None:
                db.add(LeagueCapParameters(**values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)
            print(f"loaded cap parameters {doc['league_year']} from {path.name}")
        db.commit()


def main() -> None:
    configure_logging()
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    command = sys.argv[1]

    from app.ingestion import jobs

    single_jobs: dict[str, Callable[..., int]] = {
        "sync-teams": jobs.sync_teams,
        "sync-players": jobs.sync_players,
        "sync-rosters": jobs.sync_rosters,
        "sync-standings": jobs.sync_standings,
        "sync-player-stats": jobs.sync_player_stats,
        "sync-team-stats": jobs.sync_team_stats,
        "sync-games": jobs.sync_games,
        "sync-contracts": jobs.sync_contracts,
    }

    if command == "seed-config":
        seed_config()
    elif command == "contract-coverage":
        from app.ingestion.contract_coverage import (
            contract_coverage,
            roster_side_unmatched,
            summarize,
        )

        settings = get_settings()
        with SessionLocal() as db:
            coverage = contract_coverage(db, settings.current_season, settings.cap_league_year)
            uncovered = roster_side_unmatched(db, settings.current_season, settings.cap_league_year)
        print(json.dumps({**coverage, "roster_players_without_salary": uncovered}, indent=2, default=str))
        print("\n" + summarize(coverage, uncovered))
    elif command == "purge-fixtures":
        from app.ingestion.fixtures import purge_fixtures

        apply = "--apply" in sys.argv[2:]
        with SessionLocal() as db:
            summary = purge_fixtures(db, dry_run=not apply)
        print(json.dumps(summary, indent=2, default=str))
        if not apply:
            print("\nDry run. Re-run with --apply to delete these rows.")
    elif command == "seed-demo":
        from app.ingestion.demo_seed import DemoSeedRefused, seed_demo

        try:
            with SessionLocal() as db:
                summary = seed_demo(db)
        except DemoSeedRefused as exc:
            print(f"seed-demo refused: {exc}")
            sys.exit(2)
        print(json.dumps(summary, indent=2, default=str))
    elif command == "sync-all":
        with SessionLocal() as db:
            results = jobs.sync_all(db)
        print(json.dumps(results, indent=2, default=str))
    elif command in single_jobs:
        with SessionLocal() as db:
            rows = single_jobs[command](db)
        print(f"{command}: {rows} rows")
    elif command == "index-assets":
        from app.assets.indexer import index_assets

        with SessionLocal() as db:
            summary = index_assets(db)
        print(json.dumps(summary, indent=2, default=str))
    elif command == "import-stats-csv":
        from app.ingestion.stats_csv import import_stats_csv

        csv_path = sys.argv[2] if len(sys.argv) > 2 else "../data/imports/nba_player_stats_2026.csv"
        with SessionLocal() as db:
            summary = import_stats_csv(db, csv_path)
        print(json.dumps(summary, indent=2, default=str))
    elif command == "import-kaggle":
        from app.integrations.kaggle_nba.importer import import_history

        with SessionLocal() as db:
            summary = import_history(db)
        print(json.dumps(summary, indent=2, default=str))
    elif command == "validate-data":
        from app.ingestion.quality import validate_data

        with SessionLocal() as db:
            issues = validate_data(db)
        print(json.dumps(issues, indent=2, default=str))
    elif command == "build-features":
        from app.analytics.features import build_features

        with SessionLocal() as db:
            summary = build_features(db)
        print(json.dumps(summary, indent=2, default=str))
    elif command == "train":
        from app.analytics.train import train_all

        with SessionLocal() as db:
            summary = train_all(db)
        print(json.dumps(summary, indent=2, default=str))
    elif command == "score":
        from app.analytics.score import score_all

        with SessionLocal() as db:
            summary = score_all(db)
        print(json.dumps(summary, indent=2, default=str))
    else:
        print(f"unknown command: {command}\n{__doc__}")
        sys.exit(1)

    _ = get_settings()


if __name__ == "__main__":
    main()
