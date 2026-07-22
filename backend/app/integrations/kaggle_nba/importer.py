"""Kaggle historical NBA database importer (wyattowalsh/basketball).

The dataset ships a multi-GB ``nba.sqlite`` with game-level history and identity
tables. We use it strictly as a *secondary* enrichment source:

- Existing players (matched on ``person_id == players.nba_player_id``) get draft
  and bio fields filled ONLY where they are currently NULL. nba_api-sourced values
  are never overwritten (source hierarchy); disagreements are recorded as
  ``kaggle_source_conflict`` DataQualityIssue rows instead.
- Absence of the dataset is an honest, recorded state — ``import_history`` returns
  ``{"status": "unavailable", ...}`` with a hint and the sync run still succeeds.
- Unparseable rows are rejected and recorded, never guessed.
"""

import hashlib
import os
import re
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.logging import get_logger
from app.db.models import DataQualityIssue, DataSource, DataSyncRun, Player
from app.ingestion.runs import sync_run

logger = get_logger(__name__)

DATASET_HANDLE = "wyattowalsh/basketball"
SQLITE_FILENAME = "nba.sqlite"
DATA_SOURCE_NAME = "kaggle_basketball"

UNAVAILABLE_HINT = (
    "Kaggle dataset not available locally and download did not complete. The dataset "
    "is public (no Kaggle credentials required), but kagglehub needs network access to "
    "kaggle.com and several GB of disk; restricted networks may additionally require "
    "KAGGLE_USERNAME/KAGGLE_KEY. Set kaggle_data_dir (exported as KAGGLEHUB_CACHE) to "
    "point at an existing cache. See docs/kaggle-setup.md."
)

_HEIGHT_RE = re.compile(r"^\s*(\d{1,2})\s*-\s*(\d{1,2})\s*$")

# players column -> draft_history source column
_DRAFT_FIELDS = {
    "draft_year": "season",
    "draft_round": "round_number",
    "draft_number": "overall_pick",
}


def _classify_failure(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}".lower()
    if any(t in text for t in ("401", "403", "unauthorized", "forbidden", "credential", "auth")):
        return "auth"
    if any(t in text for t in ("timed out", "timeout", "connection", "resolve", "network", "dns")):
        return "network"
    if any(t in text for t in ("404", "not found")):
        return "not_found"
    if any(t in text for t in ("no space", "disk")):
        return "disk"
    return "unknown"


def _find_sqlite(root: Path) -> Path | None:
    if not root.is_dir():
        return None
    direct = root / SQLITE_FILENAME
    if direct.is_file():
        return direct
    return next((p for p in sorted(root.rglob(SQLITE_FILENAME)) if p.is_file()), None)


def locate_dataset(download: bool = True) -> Path | None:
    """Return the directory containing ``nba.sqlite``, or None on any failure.

    Never raises: download/auth/network problems are logged with a classification
    and reported to callers as absence, which ``import_history`` records honestly.
    """
    settings = get_settings()
    if settings.kaggle_data_dir:
        # kagglehub reads KAGGLEHUB_CACHE at import/call time; set it before import.
        os.environ["KAGGLEHUB_CACHE"] = settings.kaggle_data_dir

    if not download:
        cache_root = Path(os.environ.get("KAGGLEHUB_CACHE", Path.home() / ".cache" / "kagglehub"))
        candidate = cache_root / "datasets" / DATASET_HANDLE
        sqlite_path = _find_sqlite(candidate)
        if sqlite_path is None:
            logger.warning(
                "kaggle dataset not in local cache (%s) and download disabled", candidate
            )
            return None
        return sqlite_path.parent

    try:
        import kagglehub  # imported lazily so KAGGLEHUB_CACHE above takes effect

        base = Path(kagglehub.dataset_download(DATASET_HANDLE))
    except Exception as exc:  # noqa: BLE001 — absence is an honest, recorded state
        logger.warning(
            "kaggle dataset download failed [%s]: %s: %s",
            _classify_failure(exc),
            type(exc).__name__,
            exc,
        )
        return None

    sqlite_path = _find_sqlite(base)
    if sqlite_path is None:
        logger.warning("kaggle download at %s does not contain %s", base, SQLITE_FILENAME)
        return None
    return sqlite_path.parent


def inspect_schema(sqlite_path: Path) -> dict[str, list[str]]:
    """Return {table_name: [column, ...]} for the given sqlite file (read-only)."""
    with closing(sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)) as conn:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        ]
        return {
            table: [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]
            for table in tables
        }


def _sha256_first_mb(path: Path) -> str:
    with path.open("rb") as fh:
        return hashlib.sha256(fh.read(1024 * 1024)).hexdigest()


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _parse_birth_date(value: Any) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _parse_height_inches(value: Any) -> int | None:
    if value is None:
        return None
    match = _HEIGHT_RE.match(str(value))
    if match is None:
        return None
    feet, inches = int(match.group(1)), int(match.group(2))
    if inches >= 12:
        return None
    return feet * 12 + inches


def _record_conflict(
    db: Session, nba_player_id: int, field: str, existing: Any, kaggle_value: Any
) -> None:
    db.add(
        DataQualityIssue(
            check_name="kaggle_source_conflict",
            severity="warning",
            entity=f"player:{nba_player_id}",
            message=(
                f"kaggle {DATASET_HANDLE} disagrees on {field}: existing={existing!r} "
                f"kaggle={kaggle_value!r}; existing value kept (source hierarchy)"
            ),
        )
    )


def _record_rejects(db: Session, table: str, rejected: list[str]) -> None:
    if not rejected:
        return
    db.add(
        DataQualityIssue(
            check_name="kaggle_unparseable_row",
            severity="warning",
            entity=f"kaggle:{table}",
            message=(
                f"{len(rejected)} unparseable row(s) rejected from {table} "
                f"(never guessed); samples: {'; '.join(rejected[:5])}"
            ),
        )
    )


def _enrich(
    db: Session,
    players: dict[int, Player],
    table: str,
    rows: list[dict[str, Any]],
    rejected: list[str],
    updated_ids: set[int],
) -> dict[str, int]:
    """Fill NULL player fields from parsed kaggle rows; never overwrite non-NULL."""
    counts = {"rows": 0, "matched": 0, "players_updated": 0, "fields_filled": 0, "conflicts": 0}
    for row in rows:
        counts["rows"] += 1
        person_id = _parse_int(row.get("person_id"))
        if person_id is None:
            rejected.append(f"person_id={row.get('person_id')!r}")
            continue
        player = players.get(person_id)
        if player is None:
            continue
        counts["matched"] += 1
        updated = False
        for field, kaggle_value in row.items():
            if field == "person_id" or kaggle_value is None:
                continue
            existing = getattr(player, field)
            if existing is None:
                setattr(player, field, kaggle_value)
                counts["fields_filled"] += 1
                updated = True
            elif existing != kaggle_value:
                _record_conflict(db, person_id, field, existing, kaggle_value)
                counts["conflicts"] += 1
        if updated:
            counts["players_updated"] += 1
            updated_ids.add(person_id)
    counts["rejected"] = len(rejected)
    _record_rejects(db, table, rejected)
    return counts


def _convert(
    record: dict[str, Any],
    field_map: dict[str, tuple[str, Any]],
    rejected: list[str],
) -> dict[str, Any]:
    """Parse source columns into player fields; present-but-unparseable values are
    rejected (recorded, never guessed) and become None."""
    row: dict[str, Any] = {"person_id": record.get("person_id")}
    for player_field, (src, parser) in field_map.items():
        raw = record.get(src)
        parsed = parser(raw)
        if raw is not None and str(raw).strip() and parsed is None:
            rejected.append(f"person_id={record.get('person_id')!r} {src}={raw!r}")
        row[player_field] = parsed
    return row


def _read_draft_history(
    conn: sqlite3.Connection, columns: list[str], rejected: list[str]
) -> list[dict[str, Any]]:
    available = [src for src in ("person_id", *_DRAFT_FIELDS.values()) if src in columns]
    if "person_id" not in available:
        return []
    field_map: dict[str, tuple[str, Any]] = {
        field: (src, _parse_int) for field, src in _DRAFT_FIELDS.items() if src in available
    }
    return [
        _convert(dict(zip(available, raw, strict=True)), field_map, rejected)
        for raw in conn.execute(f"SELECT {', '.join(available)} FROM draft_history")
    ]


def _read_common_player_info(
    conn: sqlite3.Connection, columns: list[str], rejected: list[str]
) -> list[dict[str, Any]]:
    available = [src for src in ("person_id", "birthdate", "height", "weight") if src in columns]
    if "person_id" not in available:
        return []
    parsers: dict[str, tuple[str, Any]] = {
        "birth_date": ("birthdate", _parse_birth_date),
        "height_inches": ("height", _parse_height_inches),
        "weight_lbs": ("weight", _parse_int),
    }
    field_map = {field: spec for field, spec in parsers.items() if spec[0] in available}
    return [
        _convert(dict(zip(available, raw, strict=True)), field_map, rejected)
        for raw in conn.execute(f"SELECT {', '.join(available)} FROM common_player_info")
    ]


def _register_data_source(db: Session, sqlite_path: Path, retrieved_at: datetime) -> str:
    checksum = _sha256_first_mb(sqlite_path)
    notes = (
        f"path={sqlite_path} sha256_first_1mb={checksum} downloaded_at={retrieved_at.isoformat()}"
    )
    source = db.scalar(select(DataSource).where(DataSource.name == DATA_SOURCE_NAME))
    if source is None:
        db.add(DataSource(name=DATA_SOURCE_NAME, upstream=DATASET_HANDLE, notes=notes))
    else:
        source.upstream = DATASET_HANDLE
        source.notes = notes
    return checksum


def import_history(
    db: Session, sqlite_path: Path | None = None, download: bool = True
) -> dict[str, Any]:
    """Enrich existing players from the Kaggle historical database.

    Reads ONLY draft_history and common_player_info (defensively, via
    inspect_schema — the upstream schema may drift). Returns a summary dict;
    when the dataset is unavailable the run still succeeds and the summary says so.
    """
    with sync_run(db, "import_kaggle_history") as run:
        if sqlite_path is None:
            located = locate_dataset(download=download)
            if located is not None:
                sqlite_path = located / SQLITE_FILENAME
        elif sqlite_path.is_dir():
            sqlite_path = sqlite_path / SQLITE_FILENAME

        if sqlite_path is None or not sqlite_path.is_file():
            run.detail = {"note": "kaggle dataset not available", "hint": UNAVAILABLE_HINT}
            db.commit()
            return {"status": "unavailable", "hint": UNAVAILABLE_HINT}

        return _import_from_sqlite(db, run, sqlite_path)


def _import_from_sqlite(db: Session, run: DataSyncRun, sqlite_path: Path) -> dict[str, Any]:
    now = datetime.now(UTC)
    schema = inspect_schema(sqlite_path)
    players = {p.nba_player_id: p for p in db.scalars(select(Player)).all()}

    tables: dict[str, dict[str, int]] = {}
    missing_tables: list[str] = []
    updated_ids: set[int] = set()  # distinct players enriched across all tables
    readers = {
        "draft_history": _read_draft_history,
        "common_player_info": _read_common_player_info,
    }
    with closing(sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)) as conn:
        for table, reader in readers.items():
            if table not in schema:
                missing_tables.append(table)
                logger.warning("kaggle table missing (schema drift?): %s", table)
                continue
            if "person_id" not in schema[table]:
                # Table exists but lacks person_id — nothing can be matched honestly.
                missing_tables.append(table)
                logger.warning("kaggle table %s unusable: no person_id column", table)
                continue
            rejected: list[str] = []
            rows = reader(conn, schema[table], rejected)
            tables[table] = _enrich(db, players, table, rows, rejected, updated_ids)

    checksum = _register_data_source(db, sqlite_path, now)

    summary: dict[str, Any] = {
        "status": "succeeded",
        "sqlite_path": str(sqlite_path),
        "sha256_first_1mb": checksum,
        "tables": tables,
        "missing_tables": missing_tables,
        "conflicts": sum(c["conflicts"] for c in tables.values()),
        "players_updated": len(updated_ids),
    }
    run.rows_written = summary["players_updated"]
    run.detail = summary
    db.commit()
    return summary
