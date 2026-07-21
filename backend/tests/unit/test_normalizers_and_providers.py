"""Provider normalization, error classification, contract file provider, cache."""

from datetime import date
from pathlib import Path

import pandas as pd

from app.core.cache import InProcessTTLCache
from app.integrations.contracts.file_provider import FileContractProvider
from app.integrations.nba_api.exceptions import (
    ProviderBlockedError,
    ProviderThrottledError,
    ProviderTimeoutError,
    classify_exception,
)
from app.integrations.nba_api.normalizers import (
    normalize_game_log,
    normalize_roster_row,
    normalize_standing_row,
    parse_experience,
    parse_height_inches,
)
from app.integrations.nba_api.schemas import validate_dataframe


class TestParsers:
    def test_height(self):
        assert parse_height_inches("6-8") == 80
        assert parse_height_inches("7-0") == 84
        assert parse_height_inches(None) is None
        assert parse_height_inches("tall") is None  # malformed → None, never guessed

    def test_experience_rookie_marker(self):
        assert parse_experience("R") == 0
        assert parse_experience("7") == 7
        assert parse_experience(None) is None


class TestRosterNormalizer:
    def test_full_row(self):
        row = pd.Series(
            {
                "TeamID": 1610612738,
                "PLAYER_ID": 1628369,
                "PLAYER": "Test Fixture Player",
                "NUM": "0",
                "POSITION": "F-G",
                "HEIGHT": "6-8",
                "WEIGHT": "210",
                "BIRTH_DATE": "MAR 03, 1998",
                "AGE": 28.0,
                "EXP": "8",
            }
        )
        out = normalize_roster_row(row, "2025-26")
        assert out["nba_player_id"] == 1628369
        assert out["height_inches"] == 80
        assert out["birth_date"] == date(1998, 3, 3)
        assert out["years_experience"] == 8
        assert out["source_record_id"] == "1610612738:1628369:2025-26"


class TestStandingNormalizer:
    def test_row(self):
        row = pd.Series(
            {
                "TeamID": 1610612749,
                "WINS": 55,
                "LOSSES": 27,
                "WinPCT": 0.671,
                "Conference": "East",
                "PlayoffRank": 2,
                "Division": "Central",
                "Record": "55-27",
            }
        )
        out = normalize_standing_row(row, "2025-26")
        assert out["wins"] == 55 and out["conference"] == "East"
        assert out["details"]["Record"] == "55-27"


class TestGameLogNormalizer:
    def test_two_rows_become_one_game(self):
        df = pd.DataFrame(
            [
                {
                    "GAME_ID": "0022500001",
                    "TEAM_ID": 1,
                    "GAME_DATE": "2025-10-21",
                    "MATCHUP": "AAA vs. BBB",
                    "WL": "W",
                    "PTS": 120,
                },
                {
                    "GAME_ID": "0022500001",
                    "TEAM_ID": 2,
                    "GAME_DATE": "2025-10-21",
                    "MATCHUP": "BBB @ AAA",
                    "WL": "L",
                    "PTS": 110,
                },
            ]
        )
        games = normalize_game_log(df, "2025-26")
        assert len(games) == 1
        game = games[0]
        assert game["home_nba_team_id"] == 1 and game["home_score"] == 120
        assert game["away_nba_team_id"] == 2 and game["away_score"] == 110


class TestSchemaValidation:
    def test_missing_columns_raise_schema_error(self):
        from app.integrations.nba_api.exceptions import ProviderSchemaError

        df = pd.DataFrame({"TeamID": [1]})
        try:
            validate_dataframe("LeagueStandingsV3", df)
            raise AssertionError("expected ProviderSchemaError")
        except ProviderSchemaError as exc:
            assert "missing required columns" in str(exc)

    def test_unknown_endpoint_passes_through(self):
        df = pd.DataFrame({"anything": [1]})
        assert validate_dataframe("SomeNewEndpoint", df) is df


class TestErrorClassification:
    def test_timeout(self):
        error = classify_exception("X", TimeoutError("Read timed out"))
        assert isinstance(error, ProviderTimeoutError)

    def test_access_denied_html_is_blocked(self):
        error = classify_exception("X", ValueError("Expecting value: line 1 (JSONDecodeError)"))
        assert isinstance(error, ProviderBlockedError)

    def test_connection_reset_is_throttled(self):
        error = classify_exception("X", ConnectionError("Connection reset by peer"))
        assert isinstance(error, ProviderThrottledError)


class TestContractFileProvider:
    HEADER = (
        "player_name,nba_player_id,team_abbreviation,season,salary,contract_type,"
        "signed_date,no_trade_clause,player_option,team_option,guaranteed,"
        "source_name,source_date\n"
    )

    def _write(self, tmp_path: Path, rows: str) -> FileContractProvider:
        path = tmp_path / "contracts.csv"
        path.write_text(self.HEADER + rows)
        return FileContractProvider(str(path))

    def test_valid_rows_parsed(self, tmp_path):
        provider = self._write(
            tmp_path,
            'Test Fixture Player,1628369,BOS,2026-27,"30,000,000",standard,'
            "2024-07-06,true,false,,30000000,Test Source,2026-07-01\n",
        )
        records = provider.fetch_contracts()
        assert len(records) == 1
        record = records[0]
        assert record.salary == 30_000_000
        assert record.no_trade_clause is True
        assert record.source_name == "Test Source"
        assert provider.rejected_rows == []

    def test_implausible_salary_rejected_not_corrected(self, tmp_path):
        provider = self._write(
            tmp_path, "Bad Row,,BOS,2026-27,999999999999,,,,,,,Test Source,2026-07-01\n"
        )
        assert provider.fetch_contracts() == []
        assert len(provider.rejected_rows) == 1

    def test_missing_required_columns_raise(self, tmp_path):
        path = tmp_path / "contracts.csv"
        path.write_text("player_name,salary\nA,1\n")
        provider = FileContractProvider(str(path))
        try:
            provider.fetch_contracts()
            raise AssertionError("expected ValueError")
        except ValueError as exc:
            assert "missing required columns" in str(exc)


class TestCache:
    def test_ttl_expiry(self, monkeypatch):
        cache = InProcessTTLCache()
        clock = {"t": 0.0}
        monkeypatch.setattr("app.core.cache.time.monotonic", lambda: clock["t"])
        cache.set("k", "v", ttl_seconds=10)
        assert cache.get("k") == "v"
        clock["t"] = 11.0
        assert cache.get("k") is None
