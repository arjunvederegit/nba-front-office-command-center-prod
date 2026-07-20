"""Expected response shapes per endpoint.

NBA.com changes schemas without notice; every production endpoint declares the dataset
and columns it depends on. Validation failures raise ProviderSchemaError instead of
letting silently-wrong data reach the database. Contract tests exercise these against
the live API on a manual/scheduled workflow only."""

from dataclasses import dataclass

import pandas as pd

from .exceptions import ProviderSchemaError


@dataclass(frozen=True)
class EndpointContract:
    endpoint: str
    dataset: str
    required_columns: tuple[str, ...]


CONTRACTS: dict[str, EndpointContract] = {
    c.endpoint: c
    for c in [
        EndpointContract(
            "CommonTeamRoster",
            "CommonTeamRoster",
            ("TeamID", "PLAYER", "PLAYER_ID", "POSITION", "HEIGHT", "WEIGHT", "AGE", "EXP"),
        ),
        EndpointContract(
            "LeagueStandingsV3",
            "Standings",
            ("TeamID", "WINS", "LOSSES", "WinPCT", "Conference", "PlayoffRank"),
        ),
        EndpointContract(
            "LeagueDashPlayerStats",
            "LeagueDashPlayerStats",
            ("PLAYER_ID", "PLAYER_NAME", "TEAM_ID", "GP", "MIN"),
        ),
        EndpointContract(
            "LeagueDashTeamStats",
            "LeagueDashTeamStats",
            ("TEAM_ID", "TEAM_NAME", "GP"),
        ),
        EndpointContract(
            "LeagueGameLog",
            "LeagueGameLog",
            ("GAME_ID", "TEAM_ID", "GAME_DATE", "MATCHUP", "WL", "PTS"),
        ),
        EndpointContract(
            "PlayerEstimatedMetrics",
            "PlayerEstimatedMetrics",
            ("PLAYER_ID", "E_OFF_RATING", "E_DEF_RATING", "E_NET_RATING"),
        ),
    ]
}


def validate_dataframe(endpoint: str, df: pd.DataFrame) -> pd.DataFrame:
    contract = CONTRACTS.get(endpoint)
    if contract is None:
        return df
    missing = [c for c in contract.required_columns if c not in df.columns]
    if missing:
        raise ProviderSchemaError(
            endpoint, f"missing required columns {missing}; got {list(df.columns)[:20]}"
        )
    if df.empty:
        raise ProviderSchemaError(endpoint, "response contained zero rows")
    return df
