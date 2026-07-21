"""Background scheduler for containerized deployments (`docker compose up`).

Plain APScheduler over the same idempotent jobs the CLI runs — a deliberate,
documented simplification over Celery/RQ (see docs/decision-log.md): jobs are
CPU-light I/O batches on a small schedule, and every job is safe to re-run.
Schedules are configurable via environment variables."""

import os

from apscheduler.schedulers.blocking import BlockingScheduler

from app.core.logging import configure_logging, get_logger
from app.db.base import SessionLocal

configure_logging()
logger = get_logger(__name__)


def run_job(job_name: str) -> None:
    from app.ingestion import jobs

    job_map = {
        "sync_rosters": jobs.sync_rosters,
        "sync_standings": jobs.sync_standings,
        "sync_player_stats": jobs.sync_player_stats,
        "sync_team_stats": jobs.sync_team_stats,
        "sync_games": jobs.sync_games,
        "sync_contracts": jobs.sync_contracts,
    }
    with SessionLocal() as db:
        try:
            rows = job_map[job_name](db)
            logger.info("worker job %s wrote %s rows", job_name, rows, extra={"job": job_name})
        except Exception:
            logger.exception("worker job %s failed", job_name, extra={"job": job_name})


def main() -> None:
    scheduler = BlockingScheduler(timezone="UTC")
    roster_hours = int(os.environ.get("SYNC_ROSTERS_EVERY_HOURS", "6"))
    stats_hours = int(os.environ.get("SYNC_STATS_EVERY_HOURS", "24"))

    scheduler.add_job(run_job, "interval", hours=roster_hours, args=["sync_rosters"])
    scheduler.add_job(run_job, "interval", hours=roster_hours, args=["sync_standings"])
    scheduler.add_job(run_job, "interval", hours=stats_hours, args=["sync_player_stats"])
    scheduler.add_job(run_job, "interval", hours=stats_hours, args=["sync_team_stats"])
    scheduler.add_job(run_job, "interval", hours=stats_hours, args=["sync_games"])
    scheduler.add_job(run_job, "interval", hours=stats_hours, args=["sync_contracts"])
    logger.info(
        "worker started (rosters/standings every %dh, stats/games daily)", roster_hours
    )
    scheduler.start()


if __name__ == "__main__":
    main()
