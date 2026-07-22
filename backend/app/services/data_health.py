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

    from app.assets.indexer import coverage as asset_coverage

    assets = asset_coverage(db)

    def latest_run(job: str) -> dict | None:
        for run in recent_runs:
            if run["job"] == job and run["status"] == "succeeded":
                return run
        return None

    nba_fresh = (
        last_success is not None
        and (now - last_success.replace(tzinfo=UTC))
        < timedelta(seconds=settings.nba_api_stale_after_seconds * 2)
        if last_success
        else False
    )

    csv_run = latest_run("import_stats_csv")
    kaggle_run = latest_run("import_kaggle_history")
    assets_run = latest_run("index_assets")
    contracts_run = latest_run("sync_contracts")
    contracts_rows = int(tables.get("contracts", {}).get("rows") or 0)

    # Fan-readable source cards: status ∈ fresh|stale|derived|incomplete|unavailable|failed
    source_cards = [
        {
            "key": "current_nba_data",
            "title": "Current NBA data",
            "status": "fresh" if nba_fresh else ("stale" if last_success else "unavailable"),
            "last_update": last_success.isoformat() if last_success else None,
            "coverage": f"{tables.get('rosters', {}).get('rows', 0)} roster spots · "
            f"{tables.get('player_season_stats', {}).get('rows', 0)} stat rows",
            "source": f"NBA.com via nba_api {nba_api_pkg.__version__}",
            "action": None if nba_fresh else "Run `make sync-data` to refresh from NBA.com.",
        },
        {
            "key": "contracts",
            "title": "Contracts & salaries",
            "status": "fresh"
            if contract_provider is not None and contracts_rows > 0
            else "unavailable",
            "last_update": contracts_run["finished_at"] if contracts_run else None,
            "coverage": f"{contracts_rows} contracts on file",
            "source": contract_provider.name if contract_provider else "not configured",
            "action": None
            if contract_provider is not None and contracts_rows > 0
            else "Download the Basketball-Reference contracts page to "
            "data/imports/contracts/players.html, set CONTRACT_DATA_PROVIDER=bbref_snapshot, "
            "then run `make sync-data`. Salary rules stay unavailable until then.",
        },
        {
            "key": "player_photos",
            "title": "Player photos",
            "status": "derived"
            if assets.get("rostered_players_with_photo", 0) > 0
            else "unavailable",
            "last_update": assets_run["finished_at"] if assets_run else None,
            "coverage": f"{round(100 * assets.get('player_photo_coverage', 0))}% of rostered players",
            "source": "local image dataset (name→ID resolved; unmatched kept for review)",
            "action": None
            if assets.get("rostered_players_with_photo", 0) > 0
            else "Place image folders at ./nbaplayerimages and run `make index-assets`.",
        },
        {
            "key": "team_logos",
            "title": "Team logos",
            "status": "derived" if assets.get("teams_with_logo", 0) >= 30 else "incomplete",
            "last_update": assets_run["finished_at"] if assets_run else None,
            "coverage": f"{assets.get('teams_with_logo', 0)}/30 teams",
            "source": "local logo dataset (CC0)",
            "action": None
            if assets.get("teams_with_logo", 0) >= 30
            else "Run `make index-assets`.",
        },
        {
            "key": "historical_database",
            "title": "Historical database",
            "status": "derived" if kaggle_run else "unavailable",
            "last_update": kaggle_run["finished_at"] if kaggle_run else None,
            "coverage": "player bio/draft enrichment"
            + (" + current-season totals CSV" if csv_run else ""),
            "source": "Kaggle wyattowalsh/basketball + user CSV import",
            "action": None if kaggle_run else "Run `make import-kaggle` (multi-GB download).",
        },
        {
            "key": "models",
            "title": "Models & evaluation",
            "status": "fresh" if models else "unavailable",
            "last_update": models[0]["trained_at"] if models else None,
            "coverage": f"{len(models)} active models",
            "source": "trained locally on ingested data (validation metrics below)",
            "action": None if models else "Run `make train && make score`.",
        },
    ]

    return {
        "generated_at": now.isoformat(),
        "current_season": settings.current_season,
        "cap_league_year": settings.cap_league_year,
        "source_cards": source_cards,
        "asset_coverage": assets,
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
