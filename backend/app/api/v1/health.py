from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import AdminDep
from app.db.base import get_db
from app.services.data_health import data_health

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/readiness")
def readiness(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ready", "database": "ok"}


@router.get("/data-health")
def get_data_health(db: Session = Depends(get_db)) -> dict:
    return data_health(db)


@router.post("/admin/sync", dependencies=[AdminDep])
def admin_sync(db: Session = Depends(get_db)) -> dict:
    """Trigger a full provider-backed refresh. Protected by ADMIN_TOKEN so anonymous
    demo users cannot exhaust NBA.com quota."""
    from app.ingestion.jobs import sync_all

    return sync_all(db)
