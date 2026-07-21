"""User-imported contract file provider (see data/contracts/README.md).

Rows failing validation are rejected — recorded, never silently corrected."""

import csv
from datetime import date, datetime
from pathlib import Path

from app.core.logging import get_logger

from . import ContractRecord

logger = get_logger(__name__)

REQUIRED_COLUMNS = {
    "player_name",
    "team_abbreviation",
    "season",
    "salary",
    "source_name",
    "source_date",
}


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_bool(value: str | None) -> bool | None:
    if value is None or value == "":
        return None
    return value.strip().lower() in ("true", "1", "yes", "y")


class FileContractProvider:
    name = "file"

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.rejected_rows: list[dict] = []

    def fetch_contracts(self) -> list[ContractRecord]:
        path = Path(self.file_path)
        if not path.exists():
            raise FileNotFoundError(
                f"CONTRACT_DATA_FILE points to {self.file_path}, which does not exist"
            )
        records: list[ContractRecord] = []
        with path.open(newline="") as fh:
            reader = csv.DictReader(fh)
            missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"contract file missing required columns: {sorted(missing)}")
            for line_no, row in enumerate(reader, start=2):
                try:
                    salary = int(str(row["salary"]).replace(",", "").replace("$", ""))
                    if salary <= 0 or salary > 100_000_000:
                        raise ValueError(f"implausible salary {salary}")
                    source_date = _parse_date(row.get("source_date"))
                    if source_date is None:
                        raise ValueError("source_date is required and must parse")
                    records.append(
                        ContractRecord(
                            player_name=row["player_name"].strip(),
                            nba_player_id=int(row["nba_player_id"])
                            if row.get("nba_player_id")
                            else None,
                            team_abbreviation=row["team_abbreviation"].strip().upper(),
                            season=row["season"].strip(),
                            salary=salary,
                            contract_type=(row.get("contract_type") or "standard").strip(),
                            signed_date=_parse_date(row.get("signed_date")),
                            no_trade_clause=_parse_bool(row.get("no_trade_clause")),
                            player_option=_parse_bool(row.get("player_option")),
                            team_option=_parse_bool(row.get("team_option")),
                            guaranteed=int(row["guaranteed"]) if row.get("guaranteed") else None,
                            source_name=row["source_name"].strip(),
                            source_date=source_date,
                        )
                    )
                except (ValueError, KeyError) as exc:
                    self.rejected_rows.append({"line": line_no, "error": str(exc)})
                    logger.warning("rejected contract row %d: %s", line_no, exc)
        return records
