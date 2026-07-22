"""Basketball-Reference contracts snapshot provider parsing tests.

All data comes from tests/fixtures/bbref_contracts_sample.html — a clearly
synthetic fixture (fake "Fixture ..." names), never real NBA data.
"""

from datetime import date
from pathlib import Path

import pytest

from app.integrations.contracts.bbref_provider import BasketballReferenceSnapshotProvider

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "bbref_contracts_sample.html"


@pytest.fixture
def provider() -> BasketballReferenceSnapshotProvider:
    return BasketballReferenceSnapshotProvider(str(FIXTURE))


def _by_player(records) -> dict[str, list]:
    out: dict[str, list] = {}
    for record in records:
        out.setdefault(record.player_name, []).append(record)
    return out


class TestBBRefSnapshotProvider:
    def test_record_count_and_players(self, provider):
        records = provider.fetch_contracts()
        assert len(records) == 6
        players = _by_player(records)
        assert set(players) == {
            "Fixture Maxplayer",
            "Fixture Teamoption",
            "Fixture Suncoder",
            "Fixture Ghostrow",
        }
        # one record per (player, season) with a salary value
        assert len(players["Fixture Maxplayer"]) == 2
        assert len(players["Fixture Teamoption"]) == 1

    def test_salary_values_and_seasons_from_header(self, provider):
        records = provider.fetch_contracts()
        maxplayer = {r.season: r for r in _by_player(records)["Fixture Maxplayer"]}
        assert set(maxplayer) == {"2025-26", "2026-27"}  # empty y3 cell skipped
        assert maxplayer["2025-26"].salary == 40_000_000
        assert maxplayer["2026-27"].salary == 43_000_000
        teamoption = _by_player(records)["Fixture Teamoption"][0]
        assert teamoption.salary == 12_345_678 and teamoption.season == "2025-26"

    def test_league_year_labels_derived_from_header_not_hardcoded(self, provider, tmp_path):
        # Relabel the header's first salary column; parsed seasons must follow it.
        html = FIXTURE.read_text(encoding="utf-8").replace("2025-26", "2031-32")
        path = tmp_path / "relabeled.html"
        path.write_text(html, encoding="utf-8")
        records = BasketballReferenceSnapshotProvider(str(path)).fetch_contracts()
        seasons = {r.season for r in records}
        assert "2031-32" in seasons
        assert "2025-26" not in seasons

    def test_option_flags_from_cell_classes(self, provider):
        records = provider.fetch_contracts()
        players = _by_player(records)
        maxplayer = {r.season: r for r in players["Fixture Maxplayer"]}
        # plain cell: no option
        assert maxplayer["2025-26"].player_option is False
        assert maxplayer["2025-26"].team_option is False
        # salary-pl: player option
        assert maxplayer["2026-27"].player_option is True
        assert maxplayer["2026-27"].team_option is False
        # salary-tm: team option
        teamoption = players["Fixture Teamoption"][0]
        assert teamoption.player_option is False
        assert teamoption.team_option is True
        # salary-et: neither flag fits — left unknown
        ghost = {r.season: r for r in players["Fixture Ghostrow"]}
        assert ghost["2026-27"].player_option is None
        assert ghost["2026-27"].team_option is None

    def test_bbref_team_codes_mapped_to_nba_abbreviations(self, provider):
        records = provider.fetch_contracts()
        teams = {r.player_name: r.team_abbreviation for r in records}
        assert teams["Fixture Maxplayer"] == "BKN"  # BRK -> BKN
        assert teams["Fixture Teamoption"] == "CHA"  # CHO -> CHA
        assert teams["Fixture Suncoder"] == "PHX"  # PHO -> PHX
        assert teams["Fixture Ghostrow"] == "MIA"  # pass-through

    def test_malformed_and_implausible_salaries_rejected_never_corrected(self, provider):
        records = provider.fetch_contracts()
        players = _by_player(records)
        assert "Fixture Badsalary" not in players
        assert "Fixture Toolarge" not in players
        assert len(provider.rejected_rows) == 2
        by_player = {r["player"]: r for r in provider.rejected_rows}
        assert "unparseable salary" in by_player["Fixture Badsalary"]["reason"]
        assert "implausible salary" in by_player["Fixture Toolarge"]["reason"]

    def test_row_wrapped_in_html_comment_is_parsed(self, provider):
        records = provider.fetch_contracts()
        ghost = _by_player(records).get("Fixture Ghostrow", [])
        assert {r.season for r in ghost} == {"2025-26", "2026-27"}
        assert {r.salary for r in ghost} == {8_000_000, 8_500_000}

    def test_table_wrapped_in_html_comment_is_parsed(self, tmp_path):
        html = (
            "<div id='all_player-contracts'><!--\n"
            "<table id='player-contracts'><thead><tr>"
            "<th data-stat='player'>Player</th><th data-stat='team_id'>Tm</th>"
            "<th data-stat='y1'>2025-26</th><th data-stat='remain_gtd'>Guaranteed</th>"
            "</tr></thead><tbody><tr>"
            "<td data-stat='player'><a href='/players/c/commefi01.html'>Fixture Commented</a></td>"
            "<td data-stat='team_id'>DEN</td>"
            "<td class='right salary-pl' data-stat='y1'>$9,000,000</td>"
            "<td data-stat='remain_gtd'>$9,000,000</td>"
            "</tr></tbody></table>\n-->"
            "</div>"
        )
        path = tmp_path / "commented_table.html"
        path.write_text(html, encoding="utf-8")
        records = BasketballReferenceSnapshotProvider(str(path)).fetch_contracts()
        assert len(records) == 1
        assert records[0].player_name == "Fixture Commented"
        assert records[0].salary == 9_000_000
        assert records[0].player_option is True

    def test_source_metadata_and_identity_left_to_downstream(self, provider):
        records = provider.fetch_contracts()
        expected_date = date.fromtimestamp(FIXTURE.stat().st_mtime)
        for record in records:
            assert record.source_name == "basketball-reference.com contracts snapshot"
            assert record.source_date == expected_date
            assert record.nba_player_id is None  # name matching happens downstream
            assert record.contract_type == "standard"
        maxplayer = _by_player(records)["Fixture Maxplayer"][0]
        assert maxplayer.guaranteed == 40_000_000  # contract-level remain_gtd total

    def test_missing_file_raises_helpful_error(self):
        provider = BasketballReferenceSnapshotProvider("data/imports/contracts/does-not-exist.html")
        with pytest.raises(FileNotFoundError) as exc_info:
            provider.fetch_contracts()
        message = str(exc_info.value)
        assert "does-not-exist.html" in message
        assert "basketball-reference.com/contracts/players.html" in message
