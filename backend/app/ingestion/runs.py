"""Sync-run bookkeeping: every ingestion job is wrapped in a DataSyncRun row so
/data-health can show exactly what ran, when, and how it failed.

**It is also where the cache is invalidated (R7).** `bump_data_version` used to be called
only at the end of `sync_all`, so every other route into an ingestion — the single-job CLI
commands, `import-stats-csv`, `import-transactions`, `import-draft-picks`, and R7's own
`sync-corpus-stats` — wrote rows and left the previous snapshot's derived values cached
under the old namespace. `EvaluationService._skills()` is keyed on the data version, so a
refresh of the modelling seasons through any of those paths served stale skill vectors
until something happened to call `sync_all`.

Putting it here makes it a property of *having ingested*, rather than a line a future job
has to remember to add. It fires only on success and only when rows were actually written,
so a no-op run — a contracts sync with no provider configured — does not churn the
namespace.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.cache import get_cache
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
        if run.rows_written:
            get_cache().bump_data_version()
        logger.info(
            "sync succeeded: %s rows=%d",
            job_name,
            run.rows_written,
            extra={"job": job_name, "run_id": run.id},
        )
