"""Pure functions: provider DataFrames/records → normalized internal dicts.

Normalizers never touch the database or the network, which makes them trivially
unit-testable against recorded fixtures."""

import math
from datetime import UTC, datetime
from typing import Any

import pandas as pd


def _clean(value: Any) -> Any:
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "item"):  # numpy scalar
        return value.item()
    return value


def _row_dict(row: pd.Series) -> dict[str, Any]:
    return {k: _clean(v) for k, v in row.items()}


def parse_height_inches(height: str | None) -> int | None:
    """'6-8' → 80. Returns None for malformed values rather than guessing."""
    if not height or "-" not in str(height):
        return None
    try:
        feet, inches = str(height).split("-", 1)
        return int(feet) * 12 + int(inches)
    except ValueError:
        return None


def parse_experience(exp: Any) -> int | None:
    """NBA.com uses 'R' for rookies."""
    if exp is None:
        return None
    if str(exp).strip().upper() == "R":
        return 0
    try:
        return int(exp)
    except (ValueError, TypeError):
        return None


def normalize_static_team(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "nba_team_id": int(record["id"]),
        "full_name": record["full_name"],
        "abbreviation": record["abbreviation"],
        "nickname": record["nickname"],
        "city": record["city"],
        "state": record.get("state"),
        "year_founded": record.get("year_founded"),
        "source_record_id": str(record["id"]),
    }


def normalize_static_player(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "nba_player_id": int(record["id"]),
        "full_name": record["full_name"],
        "first_name": record.get("first_name"),
        "last_name": record.get("last_name"),
        "is_active": bool(record.get("is_active", False)),
        "source_record_id": str(record["id"]),
    }


def normalize_roster_row(row: pd.Series, season: str) -> dict[str, Any]:
    r = _row_dict(row)
    birth_date = None
    raw_birth = r.get("BIRTH_DATE")
    if raw_birth:
        for fmt in ("%b %d, %Y", "%m/%d/%Y"):
            try:
                birth_date = datetime.strptime(str(raw_birth), fmt).date()
                break
            except ValueError:
                continue
    return {
        "nba_player_id": int(r["PLAYER_ID"]),
        "nba_team_id": int(r["TeamID"]),
        "player_name": r.get("PLAYER"),
        "season": season,
        "jersey_number": str(r.get("NUM")) if r.get("NUM") is not None else None,
        "position": r.get("POSITION"),
        "age": float(r["AGE"]) if r.get("AGE") is not None else None,
        "height_inches": parse_height_inches(r.get("HEIGHT")),
        "weight_lbs": int(r["WEIGHT"]) if str(r.get("WEIGHT") or "").isdigit() else None,
        "years_experience": parse_experience(r.get("EXP")),
        "birth_date": birth_date,
        "source_record_id": f"{r['TeamID']}:{r['PLAYER_ID']}:{season}",
    }


def normalize_standing_row(row: pd.Series, season: str) -> dict[str, Any]:
    r = _row_dict(row)
    return {
        "nba_team_id": int(r["TeamID"]),
        "season": season,
        "wins": int(r["WINS"]),
        "losses": int(r["LOSSES"]),
        "win_pct": float(r["WinPCT"]),
        "conference": r.get("Conference"),
        "conference_rank": int(r["PlayoffRank"]) if r.get("PlayoffRank") is not None else None,
        "playoff_rank": int(r["PlayoffRank"]) if r.get("PlayoffRank") is not None else None,
        "division": r.get("Division"),
        "details": {
            k: r.get(k)
            for k in (
                "Record",
                "HOME",
                "ROAD",
                "L10",
                "CurrentStreak",
                "PointsPG",
                "OppPointsPG",
                "DiffPointsPG",
            )
            if k in r
        },
        "source_record_id": f"{r['TeamID']}:{season}",
    }


def normalize_player_stat_row(
    row: pd.Series, season: str, stat_type: str
) -> dict[str, Any]:
    r = _row_dict(row)
    return {
        "nba_player_id": int(r["PLAYER_ID"]),
        "nba_team_id": int(r["TEAM_ID"]) if r.get("TEAM_ID") else None,
        "season": season,
        "stat_type": stat_type,
        "games_played": int(r["GP"]) if r.get("GP") is not None else None,
        "minutes": float(r["MIN"]) if r.get("MIN") is not None else None,
        "stats": r,
        "source_record_id": f"{r['PLAYER_ID']}:{season}:{stat_type}",
    }


def normalize_team_stat_row(row: pd.Series, season: str, stat_type: str) -> dict[str, Any]:
    r = _row_dict(row)
    return {
        "nba_team_id": int(r["TEAM_ID"]),
        "season": season,
        "stat_type": stat_type,
        "stats": r,
        "source_record_id": f"{r['TEAM_ID']}:{season}:{stat_type}",
    }


def normalize_game_log(df: pd.DataFrame, season: str) -> list[dict[str, Any]]:
    """Team-level game log (two rows per game) → one normalized game record each."""
    games: dict[str, dict[str, Any]] = {}
    for _, row in df.iterrows():
        r = _row_dict(row)
        game_id = str(r["GAME_ID"])
        game = games.setdefault(
            game_id,
            {
                "nba_game_id": game_id,
                "season": season,
                "game_date": datetime.strptime(str(r["GAME_DATE"]), "%Y-%m-%d").date(),
                "home_nba_team_id": None,
                "away_nba_team_id": None,
                "home_score": None,
                "away_score": None,
                "status": "final",
                "source_record_id": game_id,
            },
        )
        is_home = "vs." in str(r.get("MATCHUP", ""))
        if is_home:
            game["home_nba_team_id"] = int(r["TEAM_ID"])
            game["home_score"] = int(r["PTS"]) if r.get("PTS") is not None else None
        else:
            game["away_nba_team_id"] = int(r["TEAM_ID"])
            game["away_score"] = int(r["PTS"]) if r.get("PTS") is not None else None
    return list(games.values())


def provenance_from_meta(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_provider": "nba_api",
        "source_retrieved_at": datetime.fromtimestamp(meta["retrieved_at"], tz=UTC)
        if meta.get("retrieved_at")
        else datetime.now(UTC),
    }
