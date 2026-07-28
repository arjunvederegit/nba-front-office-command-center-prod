"""Contract data providers.

nba_api does not supply contract or salary detail, so contracts are an optional,
clearly-labeled secondary dataset. When no provider is configured the rest of the
application still works and salary-dependent features report `unavailable` — they are
never estimated or invented."""

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.config import get_settings


@dataclass
class ContractRecord:
    player_name: str
    team_abbreviation: str
    season: str
    salary: int
    nba_player_id: int | None = None
    contract_type: str = "standard"
    signed_date: date | None = None
    no_trade_clause: bool | None = None
    player_option: bool | None = None
    team_option: bool | None = None
    guaranteed: int | None = None
    source_name: str = ""
    source_date: date | None = None


class ContractProvider(Protocol):
    name: str

    def fetch_contracts(self) -> list[ContractRecord]: ...


DEFAULT_BBREF_SNAPSHOT = "data/imports/contracts/players.html"


def get_contract_provider() -> "ContractProvider | None":
    """Returns the configured provider, or None (the honest default).

    Paths resolve against the repo root (`Settings.contract_data_path`), not the process
    working directory: `make` runs backend commands from `backend/`, where a relative
    `data/imports/…` silently found nothing.
    """
    settings = get_settings()
    path = settings.contract_data_path
    if settings.contract_data_provider == "file":
        from .file_provider import FileContractProvider

        return FileContractProvider(str(path) if path else settings.contract_data_file)
    if settings.contract_data_provider == "bbref_snapshot":
        from app.config import BACKEND_DIR

        from .bbref_provider import BasketballReferenceSnapshotProvider

        return BasketballReferenceSnapshotProvider(
            str(path or (BACKEND_DIR.parent / DEFAULT_BBREF_SNAPSHOT))
        )
    return None
