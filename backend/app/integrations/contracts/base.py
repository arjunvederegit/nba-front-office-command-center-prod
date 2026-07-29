"""The contract-provider contract, in a module with no dependants inside this package.

It lives here rather than in `__init__` because the providers used to import it *from*
`__init__` (`from . import ContractRecord`) while `__init__` lazily imports the providers
back — a cycle that is harmless single-threaded and **not** harmless under a threadpool.

FastAPI runs sync endpoints in worker threads. Two concurrent requests could enter
`get_contract_provider()` at once: the first begins executing `bbref_provider`, reaches
`from . import ContractRecord`, and blocks; the second asks for
`BasketballReferenceSnapshotProvider` from a module whose class statement has not run
yet. Python's per-module import locks resolve that as an `ImportError` rather than a
deadlock, so the request fails with:

    ImportError: cannot import name 'BasketballReferenceSnapshotProvider'
                 from 'app.integrations.contracts.bbref_provider'

The defect was invisible while no provider was configured, because the lazy import never
ran. It surfaced the moment contract data was switched on — a 500 on `/teams/{id}/payroll`
under ordinary concurrent page load.
"""

from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass
class ContractRecord:
    player_name: str
    team_abbreviation: str
    season: str
    salary: int
    nba_player_id: int | None = None
    contract_type: str | None = None  # None = unknown; never defaulted to "standard"
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
