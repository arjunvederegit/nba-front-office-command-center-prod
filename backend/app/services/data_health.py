"""Data-health service: provider status, sync history, row counts, staleness, and
open quality issues — the backing for /api/v1/data-health and the frontend page."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.cache import get_cache
from app.db.models import (
    Base,
    Contract,
    DataQualityIssue,
    DataSyncRun,
    Game,
    LeagueCapParameters,
    ModelVersion,
    Player,
    PlayerImpactEstimate,
    PlayerSeasonStats,
    RosterEntry,
    Standing,
    Team,
    TeamNeed,
    TeamSeasonStats,
)
from app.integrations.contracts import get_contract_provider
from app.integrations.nba_api.health import get_provider_health


def data_health(db: Session) -> dict:
    settings = get_settings()
    now = datetime.now(UTC)
    stale_cutoff = now - timedelta(seconds=settings.nba_api_stale_after_seconds)

    tables = {}
    model: type[Base]
    for model, name in [
        (Team, "teams"),
        (Player, "players"),
        (RosterEntry, "rosters"),
        (Standing, "standings"),
        (PlayerSeasonStats, "player_season_stats"),
        (TeamSeasonStats, "team_season_stats"),
        (Game, "games"),
        (Contract, "contracts"),
        (PlayerImpactEstimate, "player_impact_estimates"),
        (TeamNeed, "team_needs"),
    ]:
        count = db.scalar(select(func.count()).select_from(model)) or 0
        last_retrieved = None
        stale = None
        if hasattr(model, "source_retrieved_at"):
            last_retrieved = db.scalar(select(func.max(model.source_retrieved_at)))
            if last_retrieved is not None:
                if last_retrieved.tzinfo is None:
                    last_retrieved = last_retrieved.replace(tzinfo=UTC)
                stale = last_retrieved < stale_cutoff
        tables[name] = {
            "rows": count,
            "last_retrieved_at": last_retrieved.isoformat() if last_retrieved else None,
            "stale": stale,
        }

    recent_runs = [
        {
            "job": r.job_name,
            "status": r.status,
            "rows": r.rows_written,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "error": f"{r.error_class}: {(r.error_message or '')[:200]}" if r.error_class else None,
        }
        for r in db.scalars(
            select(DataSyncRun).order_by(DataSyncRun.started_at.desc()).limit(25)
        ).all()
    ]
    last_success = db.scalar(
        select(func.max(DataSyncRun.finished_at)).where(DataSyncRun.status == "succeeded")
    )

    open_issues = [
        {
            "check": i.check_name,
            "severity": i.severity,
            "message": i.message,
            "detected_at": i.detected_at.isoformat() if i.detected_at else None,
        }
        for i in db.scalars(
            select(DataQualityIssue)
            .where(DataQualityIssue.resolved_at.is_(None))
            .order_by(DataQualityIssue.detected_at.desc())
            .limit(50)
        ).all()
    ]

    models = [
        {
            "name": m.model_name,
            "version": m.version,
            "algorithm": m.algorithm,
            "trained_at": m.trained_at.isoformat() if m.trained_at else None,
            "validation": m.validation_metrics,
        }
        for m in db.scalars(select(ModelVersion).where(ModelVersion.is_active)).all()
    ]

    cap_years = [
        row.league_year
        for row in db.scalars(
            select(LeagueCapParameters).order_by(LeagueCapParameters.league_year)
        ).all()
    ]

    contract_provider = get_contract_provider()
    import nba_api as nba_api_pkg

    return {
        "generated_at": now.isoformat(),
        "current_season": settings.current_season,
        "cap_league_year": settings.cap_league_year,
        "providers": {
            "nba_api": {
                "configured": True,
                "package_version": nba_api_pkg.__version__,
                "upstream": "NBA.com (stats.nba.com; live cdn disabled by default)",
                "endpoints": get_provider_health().snapshot(),
            },
            "contracts": {
                "configured": contract_provider is not None,
                "provider": contract_provider.name if contract_provider else None,
                "note": None
                if contract_provider
                else "No contract provider configured — salary features are unavailable "
                "(nba_api does not supply contracts).",
            },
            "injuries": {
                "configured": bool(settings.injury_data_provider),
                "note": None
                if settings.injury_data_provider
                else "No injury provider configured — injury status is unavailable and "
                "never fabricated; availability uses historical games played.",
            },
            "live_games": {
                "enabled": settings.live_data_enabled,
                "note": "Live scoreboard polling is disabled (offseason / cdn.nba.com "
                "unreachable states are surfaced, not hidden).",
            },
        },
        "cache_backend": get_cache().backend,
        "tables": tables,
        "cap_parameter_years": cap_years,
        "last_successful_sync": last_success.isoformat() if last_success else None,
        "recent_sync_runs": recent_runs,
        "open_quality_issues": open_issues,
        "active_models": models,
    }
