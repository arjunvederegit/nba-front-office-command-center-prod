"""Sync-run bookkeeping: every ingestion job is wrapped in a DataSyncRun row so
/data-health can show exactly what ran, when, and how it failed."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import DataSyncRun

logger = get_logger(__name__)


@contextmanager
def sync_run(db: Session, job_name: str) -> Iterator[DataSyncRun]:
    run = DataSyncRun(job_name=job_name, status="running")
    db.add(run)
    db.commit()
    logger.info("sync started: %s", job_name, extra={"job": job_name, "run_id": run.id})
    try:
        yield run
    except Exception as exc:
        db.rollback()
        run.status = "failed"
        run.finished_at = datetime.now(UTC)
        run.error_class = type(exc).__name__
        run.error_message = str(exc)[:2000]
        db.add(run)
        db.commit()
        logger.error(
            "sync failed: %s (%s)",
            job_name,
            type(exc).__name__,
            extra={"job": job_name, "run_id": run.id},
        )
        raise
    else:
        run.status = "succeeded"
        run.finished_at = datetime.now(UTC)
        db.add(run)
        db.commit()
        logger.info(
            "sync succeeded: %s rows=%d",
            job_name,
            run.rows_written,
            extra={"job": job_name, "run_id": run.id},
        )
