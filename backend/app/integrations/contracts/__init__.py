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


def get_contract_provider() -> "ContractProvider | None":
    """Returns the configured provider, or None (the honest default)."""
    settings = get_settings()
    if settings.contract_data_provider == "file":
        from .file_provider import FileContractProvider

        return FileContractProvider(settings.contract_data_file)
    return None
