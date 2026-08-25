"""User-supplied season-totals CSV importer (2025-26 stat lines).

Rows are matched to existing players strictly by official NBA ``PLAYER_ID`` — never
by name. Rows that cannot be matched or that fail plausibility checks are recorded
as DataQualityIssue rows and skipped; values are never guessed or corrected.
"""

import csv
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import DataQualityIssue, Player, PlayerSeasonStats, Team
from app.ingestion.runs import sync_run

logger = get_logger(__name__)

REQUIRED_COLUMNS: tuple[str, ...] = (
    "PLAYER_ID",
    "RANK",
    "PLAYER",
    "TEAM_ID",
    "TEAM",
    "GP",
    "MIN",
    "FGM",
    "FGA",
    "FG_PCT",
    "FG3M",
    "FG3A",
    "FG3_PCT",
    "FTM",
    "FTA",
    "FT_PCT",
    "OREB",
    "DREB",
    "REB",
    "AST",
    "STL",
    "BLK",
    "TOV",
    "PF",
    "PTS",
    "EFF",
    "AST_TOV",
    "STL_TOV",
)

# Season totals (counting stats) stored verbatim at the top level of the stats JSON.
_TOTAL_FIELDS: tuple[str, ...] = (
    "GP",
    "MIN",
    "FGM",
    "FGA",
    "FG3M",
    "FG3A",
    "FTM",
    "FTA",
    "OREB",
    "DREB",
    "REB",
    "AST",
    "STL",
    "BLK",
    "TOV",
    "PF",
    "PTS",
)

# Totals divided by GP (rounded to 2 decimals) under stats["per_game"].
_PER_GAME_FIELDS: tuple[str, ...] = (
    "MIN",
    "PTS",
    "REB",
    "AST",
    "STL",
    "BLK",
    "TOV",
    "FGA",
    "FG3A",
    "FG3M",
    "FTA",
)

# Already-derived rates copied verbatim under stats["rates"].
_RATE_FIELDS: tuple[str, ...] = ("FG_PCT", "FG3_PCT", "FT_PCT", "AST_TOV", "STL_TOV")
_PCT_FIELDS: tuple[str, ...] = ("FG_PCT", "FG3_PCT", "FT_PCT")

# QA-11, R7. Season totals that the source does not guarantee — the third category, and
# the reason this was not a one-line move.
#
# `EFF` is NBA.com's efficiency composite, `(PTS + REB + AST + STL + BLK) - (missed FG +
# missed FT + TOV)`, summed over the season. It is a **total**: 60 across 4 games is 15.0
# per game, not 60. Sitting in `_RATE_FIELDS` it was copied verbatim into `stats["rates"]`
# and rendered beside FG% and 3P% — two scale-independent quantities — so a 4-game player
# and an 82-game player were compared on a number that grows with games played, and the
# per-game view showed the season total unchanged.
#
# Moving it into `_TOTAL_FIELDS` would have been wrong for a different reason: those are
# parsed with `_required_float` and a blank `EFF` would start **rejecting the whole row**,
# where `_RATE_FIELDS`'s `_optional_float` tolerated it. A stat that is optional in the
# source must not become a reason to drop a player's season.
#
# So: parsed optionally, stored as a total, and divided by GP into `per_game` when it is
# present. Absent, it is absent from both bags rather than zero.
_OPTIONAL_TOTAL_FIELDS: tuple[str, ...] = ("EFF",)


class _RowRejected(ValueError):
    """A CSV row failed validation; it is recorded and skipped, never corrected."""


def _clean(value: float) -> int | float:
    return int(value) if value.is_integer() else value


def _required_float(row: dict[str, str], column: str) -> float:
    raw = (row.get(column) or "").strip()
    if not raw:
        raise _RowRejected(f"missing value for {column}")
    try:
        return float(raw)
    except ValueError:
        raise _RowRejected(f"unparseable value for {column}: {raw!r}") from None


def _optional_float(row: dict[str, str], column: str) -> float | None:
    raw = (row.get(column) or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        raise _RowRejected(f"unparseable value for {column}: {raw!r}") from None


def _parse_row(row: dict[str, str]) -> dict[str, Any]:
    """Parse and validate one CSV row; raises _RowRejected on any implausible value."""
    player_id_raw = (row.get("PLAYER_ID") or "").strip()
    try:
        nba_player_id = int(player_id_raw)
    except ValueError:
        raise _RowRejected(f"unparseable PLAYER_ID: {player_id_raw!r}") from None

    try:
        nba_team_id: int | None = int((row.get("TEAM_ID") or "").strip())
    except ValueError:
        nba_team_id = None  # team link is auxiliary; the stat row still imports

    totals = {field: _required_float(row, field) for field in _TOTAL_FIELDS}

    gp = totals["GP"]
    if not gp.is_integer() or not 1 <= gp <= 82:
        raise _RowRejected(f"implausible GP: {row['GP']!r} (expected integer in 1..82)")
    if totals["MIN"] < 0:
        raise _RowRejected(f"implausible MIN: {row['MIN']!r} (negative)")
    if totals["PTS"] < 0:
        raise _RowRejected(f"implausible PTS: {row['PTS']!r} (negative)")

    rates = {field: _optional_float(row, field) for field in _RATE_FIELDS}
    for field in _PCT_FIELDS:
        value = rates[field]
        if value is not None and not 0 <= value <= 1:
            raise _RowRejected(f"implausible {field}: {row[field]!r} (expected 0..1 or blank)")

    optional_totals = {
        field: value
        for field in _OPTIONAL_TOTAL_FIELDS
        if (value := _optional_float(row, field)) is not None
    }

    return {
        "nba_player_id": nba_player_id,
        "nba_team_id": nba_team_id,
        "player_name": (row.get("PLAYER") or "").strip(),
        "totals": totals,
        "optional_totals": optional_totals,
        "rates": rates,
    }


def import_stats_csv(db: Session, csv_path: str, season: str = "2025-26") -> dict:
    """Import a user-supplied season-totals CSV into PlayerSeasonStats.

    Idempotent: rows upsert on (player_id, season, stat_type="totals"). Unmatched or
    implausible rows are recorded as DataQualityIssue rows and skipped — never guessed.
    """
    with sync_run(db, "import_stats_csv") as run:
        path = Path(csv_path)
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
            if missing:
                raise ValueError(f"CSV missing required columns: {', '.join(missing)}")
            rows = list(reader)

        retrieved_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        players = {p.nba_player_id: p for p in db.scalars(select(Player)).all()}
        teams = {t.nba_team_id: t for t in db.scalars(select(Team)).all()}
        existing = {
            s.player_id: s
            for s in db.scalars(
                select(PlayerSeasonStats).where(
                    PlayerSeasonStats.season == season,
                    PlayerSeasonStats.stat_type == "totals",
                )
            ).all()
        }

        imported = unmatched = rejected = 0
        for line_no, row in enumerate(rows, start=2):
            try:
                parsed = _parse_row(row)
            except _RowRejected as exc:
                rejected += 1
                db.add(
                    DataQualityIssue(
                        check_name="csv_implausible_value",
                        severity="warning",
                        message=(
                            f"{path.name} line {line_no}: {exc} "
                            f"(PLAYER={(row.get('PLAYER') or '?').strip()!r}, "
                            f"PLAYER_ID={(row.get('PLAYER_ID') or '?').strip()}); row skipped"
                        ),
                    )
                )
                continue

            player = players.get(parsed["nba_player_id"])
            if player is None:
                unmatched += 1
                db.add(
                    DataQualityIssue(
                        check_name="csv_unmatched_player",
                        severity="warning",
                        message=(
                            f"{path.name} line {line_no}: no player with "
                            f"PLAYER_ID={parsed['nba_player_id']} "
                            f"(PLAYER={parsed['player_name']!r}); row not imported"
                        ),
                    )
                )
                continue

            totals: dict[str, float] = parsed["totals"]
            optional_totals: dict[str, float] = parsed["optional_totals"]
            gp = int(totals["GP"])
            per_game = {
                field: round(totals[field] / gp, 2) if gp > 0 else None
                for field in _PER_GAME_FIELDS
            }
            # A season total the source may omit is divided by GP like any other total,
            # and stays absent from both bags where the source omitted it.
            for field, value in optional_totals.items():
                per_game[field] = round(value / gp, 2) if gp > 0 else None
            stats: dict[str, Any] = {field: _clean(value) for field, value in totals.items()}
            stats.update({field: _clean(value) for field, value in optional_totals.items()})
            stats["per_game"] = per_game
            stats["rates"] = parsed["rates"]
            stats["source_file"] = path.name

            team = teams.get(parsed["nba_team_id"]) if parsed["nba_team_id"] is not None else None
            values: dict[str, Any] = {
                "team_id": team.id if team is not None else None,
                "games_played": gp,
                "minutes": totals["MIN"],
                "stats": stats,
                "source_provider": "user_import_csv",
                "source_record_id": f"{parsed['nba_player_id']}:{season}:totals",
                "source_retrieved_at": retrieved_at,
                "ingestion_run_id": run.id,
            }
            stat_row = existing.get(player.id)
            if stat_row is None:
                stat_row = PlayerSeasonStats(player_id=player.id, season=season, stat_type="totals")
                db.add(stat_row)
                existing[player.id] = stat_row
            for key, value in values.items():
                setattr(stat_row, key, value)
            imported += 1
            run.rows_written += 1

        db.commit()
        result = {
            "rows": len(rows),
            "imported": imported,
            "unmatched": unmatched,
            "rejected": rejected,
            "season": season,
        }
        run.detail = result
        logger.info("import_stats_csv: %s", result, extra={"run_id": run.id})
        return result
