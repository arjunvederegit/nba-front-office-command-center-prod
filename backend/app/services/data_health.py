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


def _aware(value: datetime | None) -> datetime | None:
    """Normalize to tz-aware UTC.

    `last_successful_sync` used to serialise naive while `tables[*].last_retrieved_at`
    serialised tz-aware, so the browser parsed the two on different clocks — on the exact
    path the freshness fix touches.
    """
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def data_health(db: Session) -> dict:
    settings = get_settings()
    now = datetime.now(UTC)
    stale_cutoff = now - timedelta(seconds=settings.nba_api_stale_after_seconds)

    # Tables whose freshness is a claim about NBA.com data. `contracts` is deliberately
    # absent: it comes from a user-supplied provider on its own cadence.
    NBA_TABLES = {
        "teams",
        "players",
        "rosters",
        "standings",
        "player_season_stats",
        "team_season_stats",
        "games",
    }

    tables = {}
    nba_retrieved_at: datetime | None = None
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
            last_retrieved = _aware(db.scalar(select(func.max(model.source_retrieved_at))))
            if last_retrieved is not None:
                stale = last_retrieved < stale_cutoff
            if name in NBA_TABLES:
                # Per-source, and filtered to the NBA provider. The audit suggested
                # reusing `tables[*].last_retrieved_at`, but `player_season_stats` also
                # carries CSV-import rows, so the unfiltered maximum is the CSV's
                # timestamp — still wrong, by about 25 hours.
                source_provider = model.source_provider  # type: ignore[attr-defined]
                provider_max = _aware(
                    db.scalar(
                        select(func.max(model.source_retrieved_at)).where(
                            source_provider == "nba_api"
                        )
                    )
                )
                if provider_max is not None and (
                    nba_retrieved_at is None or provider_max > nba_retrieved_at
                ):
                    nba_retrieved_at = provider_max
        tables[name] = {
            "rows": count,
            "last_retrieved_at": last_retrieved.isoformat() if last_retrieved else None,
            "stale": stale,
        }

    nba_tables_stale = [
        name
        for name, t in tables.items()
        if name in NBA_TABLES and t["stale"] is True and t["rows"]
    ]

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
    last_job_finished = _aware(
        db.scalar(
            select(func.max(DataSyncRun.finished_at)).where(DataSyncRun.status == "succeeded")
        )
    )
    # QA-4: this used to be `last_success`, the maximum finish time across *all* jobs, so
    # a local `index_assets` run made six-day-old NBA.com data read as "fresh · updated
    # Jul 27" while the real sync was Jul 21. Freshness is a property of when NBA.com
    # data was retrieved, never of when some job finished.
    last_success = nba_retrieved_at

    ISSUE_PAGE = 50
    open_issue_total = (
        db.scalar(
            select(func.count())
            .select_from(DataQualityIssue)
            .where(DataQualityIssue.resolved_at.is_(None))
        )
        or 0
    )
    open_issue_counts: dict[str, int] = {
        str(row[0]): int(row[1])
        for row in db.execute(
            select(DataQualityIssue.check_name, func.count())
            .where(DataQualityIssue.resolved_at.is_(None))
            .group_by(DataQualityIssue.check_name)
            .order_by(func.count().desc())
        ).all()
    }
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
            .limit(ISSUE_PAGE)
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

    # Invariant: NBA data is never reported fresh while any NBA table is stale. The
    # per-table `stale` flags and this headline now derive from the same timestamps, so
    # they cannot disagree.
    nba_fresh = (
        last_success is not None
        and not nba_tables_stale
        and (now - last_success) < timedelta(seconds=settings.nba_api_stale_after_seconds)
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
            "stale_tables": nba_tables_stale,
            "action": None if nba_fresh else "Run `make sync-data` to refresh from NBA.com.",
        },
        {
            "key": "contracts",
            "title": "Contracts & salaries",
            # Three distinct states, in the order they must be checked. An empty table
            # with a provider configured is *empty*, not "derived" and not "unavailable":
            # the import ran (or was never run) and produced nothing, which is a
            # different problem from having no provider at all.
            "status": (
                "unavailable"
                if contract_provider is None
                else ("fresh" if contracts_rows > 0 else "incomplete")
            ),
            "last_update": contracts_run["finished_at"] if contracts_run else None,
            "coverage": (
                f"{contracts_rows} contracts on file"
                if contracts_rows
                else (
                    "no contracts imported yet"
                    if contract_provider is not None
                    else "no contract provider configured"
                )
            ),
            "source": contract_provider.name if contract_provider else "not configured",
            "action": None
            if contract_provider is not None and contracts_rows > 0
            else (
                "A contract provider is configured but no rows were imported. Check the "
                "snapshot file and run `make import-contracts`."
                if contract_provider is not None
                else "Download the Basketball-Reference contracts page to "
                "data/imports/contracts/players.html, set "
                "CONTRACT_DATA_PROVIDER=bbref_snapshot, then run `make sync-data`. "
                "Salary rules stay unavailable until then."
            ),
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
        "last_job_finished_at": last_job_finished.isoformat() if last_job_finished else None,
        "nba_tables_stale": nba_tables_stale,
        "recent_sync_runs": recent_runs,
        "open_quality_issues": open_issues,
        # The list is capped, so without a total the real backlog is unknowable from the
        # API — 562 open rows rendered as 50 with no indication that 512 were missing.
        "open_quality_issue_total": open_issue_total,
        "open_quality_issue_counts": open_issue_counts,
        "open_quality_issues_truncated": open_issue_total > len(open_issues),
        "active_models": models,
    }
