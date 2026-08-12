"""R5-2. Pick ownership: what the source resolves, and what it must not.

The importer's job is to be *strict*. Every test here that looks like it is checking a
parser is really checking a refusal: a swap must not become an owner, a protection must
not become an owner, an unreadable team name must not become the nearest match, and a
team with one unresolved clause must not receive a Stepien verdict.
"""

import pytest
from sqlalchemy.orm import Session

from app.cba.builder import build_trade_context
from app.cba.context import PickAsset, TeamContext, TradeContext
from app.cba.engine import TradeLegalityEngine
from app.cba.rules.picks import StepienRule, _consecutive_gaps
from app.db.models import DataQualityIssue, DraftPick
from app.ingestion.draft_picks import (
    TEAM_ALIASES,
    import_draft_picks,
    ownership_summary,
    parse_snapshot,
    resolve_team,
)
from tests.conftest import make_team

SECTION = """
<h2>{team} Future Traded Pick Details</h2>
<table class="table">
<thead><tr><th>Year</th><th>Incoming</th><th>Outgoing</th></tr></thead>
<tbody>{rows}</tbody>
</table>
"""

ROW = """
<tr>
<td data-th="Year" rel="{year}">{year}</td>
<td data-th="Incoming">{incoming}</td>
<td data-th="Outgoing">{outgoing}</td>
</tr>
"""


def _para(headline: str, body: str) -> str:
    return f'<p style="margin-top: 0;">\n<strong>{headline}</strong><br>\n{body}</p>'


def _markup(team: str, year: int, incoming: str = "", outgoing: str = "") -> str:
    return SECTION.format(
        team=team, rows=ROW.format(year=year, incoming=incoming, outgoing=outgoing)
    )


class TestParsing:
    def test_an_unconditional_transfer_is_resolved(self):
        markup = _markup(
            "Atlanta Hawks",
            2027,
            outgoing=_para(
                "2027 first round draft pick to San Antonio",
                "Atlanta's 2027 1st round pick to San Antonio "
                "[Atlanta-San Antonio, 6/30/2022]",
            ),
        )
        picks = parse_snapshot(markup)
        assert len(picks) == 1
        pick = picks[0]
        assert pick.conveyance == "unconditional"
        assert (pick.original_team, pick.owning_team) == ("Atlanta", "San Antonio")
        assert (pick.draft_year, pick.round_number) == (2027, 1)

    def test_a_routing_history_does_not_make_a_pick_conditional(self):
        """"(via Golden State)" says where the pick has been, not whether it conveys."""
        for via in (
            "(via Golden State)",
            "(via Boston to Memphis)",
            "(via Atlanta; via Atlanta)",
        ):
            markup = _markup(
                "Brooklyn Nets",
                2028,
                outgoing=_para(
                    "2028 second round draft pick to Brooklyn",
                    f"Memphis' 2028 2nd round pick to Brooklyn {via} [Memphis-Brooklyn]",
                ),
            )
            picks = parse_snapshot(markup)
            assert picks[0].conveyance == "unconditional", via

    @pytest.mark.parametrize(
        ("body", "expected"),
        [
            (
                "New Orleans will receive the more favorable of its 2027 1st round pick "
                "and Milwaukee's 2027 1st round pick",
                "swap",
            ),
            (
                "Atlanta's 2027 2nd round pick to Dallas protected for selections 31-55",
                "protected",
            ),
            (
                "If the L.A. Lakers convey a 1st round pick to Memphis in 2027, then the "
                "L.A. Lakers' 2027 2nd round pick to Brooklyn",
                "conditional",
            ),
            (
                "New York's 2028 2nd round pick to Detroit; Detroit may convey this pick "
                "to Utah (see Detroit Outgoing)",
                "conditional",
            ),
        ],
    )
    def test_conditional_shapes_never_resolve_to_an_owner(self, body, expected):
        markup = _markup(
            "Atlanta Hawks", 2027, outgoing=_para("2027 first round draft pick", body)
        )
        pick = parse_snapshot(markup)[0]
        assert pick.conveyance == expected
        assert pick.original_team is None and pick.owning_team is None
        assert pick.source_text.startswith(body[:30])

    def test_nothing_in_the_real_snapshot_is_left_unclassified(self):
        """`unparsed` is the class for a sentence this importer does not understand. On
        the committed snapshot it must be empty — an unclassified entry is a silent hole
        in ownership, and the whole point is that holes are named."""
        from pathlib import Path

        from app.ingestion.draft_picks import snapshot_path

        path: Path = snapshot_path()
        if not path.is_file():
            pytest.skip("no local RealGM snapshot (data/imports/ is gitignored)")
        picks = parse_snapshot(path.read_text(encoding="utf-8", errors="replace"))
        assert len(picks) > 300
        assert [p for p in picks if p.conveyance == "unparsed"] == []


class TestTeamResolution:
    def test_the_two_los_angeles_teams_are_distinguished(self):
        assert TEAM_ALIASES["l.a. lakers"] == "LAL"
        assert TEAM_ALIASES["l.a. clippers"] == "LAC"

    def test_an_unknown_name_is_not_guessed(self, db: Session):
        team = make_team(db, 1, "ATL", "Atlanta Hawks")
        by_abbr = {"ATL": team}
        assert resolve_team("Atlanta", by_abbr) is team
        assert resolve_team("Atalanta", by_abbr) is None
        assert resolve_team("Seattle", by_abbr) is None
        assert resolve_team(None, by_abbr) is None


class TestImport:
    def _teams(self, db: Session) -> dict:
        return {
            abbr: make_team(db, 1610612700 + i, abbr, name)
            for i, (abbr, name) in enumerate(
                [("ATL", "Atlanta Hawks"), ("SAS", "San Antonio Spurs"), ("DAL", "Dallas Mavericks")]
            )
        }

    def _write(self, tmp_path, markup: str) -> str:
        path = tmp_path / "realgm.html"
        path.write_text(markup, encoding="utf-8")
        return str(path)

    def test_it_verifies_only_the_unconditional_entries(self, db: Session, tmp_path):
        self._teams(db)
        markup = _markup(
            "Atlanta Hawks",
            2027,
            outgoing=_para(
                "2027 first round draft pick to San Antonio",
                "Atlanta's 2027 1st round pick to San Antonio [x]",
            )
            + _para(
                "2027 second round draft pick to Dallas",
                "Atlanta's 2027 2nd round pick to Dallas protected for selections 31-55 [x]",
            ),
        )
        summary = import_draft_picks(db, self._write(tmp_path, markup))
        assert summary["verified"] == 1
        assert summary["unresolved"] == 1
        rows = db.query(DraftPick).all()
        verified = [r for r in rows if r.is_verified]
        assert len(verified) == 1
        assert verified[0].conveyance == "unconditional"
        unresolved = [r for r in rows if not r.is_verified]
        assert unresolved[0].conveyance == "protected"
        assert "protected for selections 31-55" in unresolved[0].source_text

    def test_every_unresolved_entry_raises_a_named_warning(self, db: Session, tmp_path):
        self._teams(db)
        markup = _markup(
            "Atlanta Hawks",
            2029,
            outgoing=_para(
                "2029 first round draft pick",
                "Atlanta will receive the less favorable of the two [x]",
            ),
        )
        import_draft_picks(db, self._write(tmp_path, markup))
        issues = db.query(DataQualityIssue).all()
        assert len(issues) == 1
        assert issues[0].check_name == "draft_pick_unresolved_conveyance"
        assert "swap conveyance" in issues[0].message

    def test_reimporting_the_same_file_is_idempotent(self, db: Session, tmp_path):
        self._teams(db)
        markup = _markup(
            "Atlanta Hawks",
            2027,
            outgoing=_para(
                "2027 first round draft pick to San Antonio",
                "Atlanta's 2027 1st round pick to San Antonio [x]",
            ),
        )
        source = self._write(tmp_path, markup)
        first = import_draft_picks(db, source)
        second = import_draft_picks(db, source)
        assert first["verified"] == second["verified"] == 1
        assert db.query(DraftPick).count() == 1
        assert (
            db.query(DataQualityIssue).filter(DataQualityIssue.resolved_at.is_(None)).count() == 0
        )

    def test_a_missing_snapshot_reports_where_to_put_one(self, db: Session, tmp_path):
        summary = import_draft_picks(db, str(tmp_path / "absent.html"))
        assert summary["imported"] == 0
        assert "hint" in summary
        assert db.query(DraftPick).count() == 0

    def test_ownership_summary_separates_retained_from_unknown(self, db: Session, tmp_path):
        teams = self._teams(db)
        markup = _markup(
            "Atlanta Hawks",
            2027,
            outgoing=_para(
                "2027 first round draft pick to San Antonio",
                "Atlanta's 2027 1st round pick to San Antonio [x]",
            ),
        ) + _markup(
            "Dallas Mavericks",
            2027,
            outgoing=_para(
                "2027 first round draft pick",
                "Dallas will receive the less favorable of the two [x]",
            ),
        )
        import_draft_picks(db, self._write(tmp_path, markup))
        summary = ownership_summary(db, 2027, 1)["teams"]
        assert summary["ATL"]["own_pick_retained"] is False
        assert summary["ATL"]["own_pick_conveyed_to"] == ["SAS"]
        assert summary["SAS"]["acquired_picks"] == 1
        assert summary["SAS"]["own_pick_retained"] is True
        assert summary["DAL"]["verified"] is False
        assert summary["DAL"]["unresolved_entries"][0]["conveyance"] == "swap"
        assert teams["DAL"].abbreviation == "DAL"


def _context(team: TeamContext) -> TradeContext:
    from app.cba.context import CapParams

    return TradeContext(
        league_year="2026-27",
        params=CapParams(
            league_year="2026-27",
            salary_cap=164_961_000,
            luxury_tax=200_428_000,
            first_apron=209_015_000,
            second_apron=221_686_000,
            minimum_team_salary=148_465_000,
            source_name="test",
        ),
        teams=[team],
    )


def _team(**kwargs) -> TeamContext:
    base = {
        "team_id": "t1",
        "abbreviation": "ATL",
        "name": "Atlanta",
        "roster_count_before": 15,
    }
    return TeamContext(**{**base, **kwargs})


def _out(year: int, round_number: int = 1) -> PickAsset:
    return PickAsset(
        from_team_id="t1",
        to_team_id="t2",
        draft_year=year,
        round_number=round_number,
        protections=None,
        is_hypothetical=True,
    )


class TestStepienRule:
    def test_no_outgoing_first_means_no_result(self):
        team = _team(picks_out=[_out(2029, round_number=2)], first_round_holdings={2029: 1})
        assert StepienRule().evaluate(_context(team)) == []

    def test_it_certifies_a_team_whose_ownership_is_resolved(self):
        team = _team(
            picks_out=[_out(2029)],
            first_round_holdings={2028: 1, 2029: 1, 2030: 1, 2031: 1},
        )
        result = StepienRule().evaluate(_context(team))[0]
        assert result.status == "pass"
        assert result.confidence == "high"
        assert result.calculation["holdings_after"][2029] == 0

    def test_it_fails_a_deal_that_empties_consecutive_drafts(self):
        team = _team(
            picks_out=[_out(2029), _out(2030)],
            first_round_holdings={2028: 1, 2029: 1, 2030: 1, 2031: 1},
        )
        result = StepienRule().evaluate(_context(team))[0]
        assert result.status == "fail"
        assert result.calculation["consecutive_gaps"] == [[2029, 2030]]

    def test_an_acquired_pick_can_fill_the_gap(self):
        team = _team(
            picks_out=[_out(2029), _out(2030)],
            picks_in=[
                PickAsset(
                    from_team_id="t2",
                    to_team_id="t1",
                    draft_year=2030,
                    round_number=1,
                    protections=None,
                    is_hypothetical=True,
                )
            ],
            first_round_holdings={2028: 1, 2029: 1, 2030: 1, 2031: 1},
        )
        assert StepienRule().evaluate(_context(team))[0].status == "pass"

    def test_one_unresolved_clause_withholds_the_verdict(self):
        """The refusal this release exists for. A team with a swap nobody can reduce has
        an ownership picture that is genuinely uncertain, and a pass would be invented."""
        team = _team(
            picks_out=[_out(2029)],
            first_round_holdings=None,
            pick_ownership_unresolved=[
                {"draft_year": 2029, "conveyance": "swap", "source_text": "more favorable of"}
            ],
        )
        result = StepienRule().evaluate(_context(team))[0]
        assert result.status == "unavailable"
        assert result.confidence == "low"
        assert "swaps, protected picks or conditional conveyances" in result.message
        assert result.calculation["unresolved_total"] == 1

    def test_no_source_at_all_still_says_so(self):
        team = _team(picks_out=[_out(2029)], first_round_holdings=None)
        result = StepienRule().evaluate(_context(team))[0]
        assert result.status == "unavailable"
        assert "no authoritative pick-ownership provider" in result.message

    def test_trading_a_pick_the_source_does_not_show_is_reported_not_assumed(self):
        team = _team(picks_out=[_out(2029)], first_round_holdings={2028: 1, 2029: 0, 2030: 1})
        result = StepienRule().evaluate(_context(team))[0]
        assert result.status == "unavailable"
        assert "the construction and the source disagree" in result.message

    def test_gap_detection_only_looks_at_adjacent_years(self):
        assert _consecutive_gaps({2027: 0, 2029: 0}) == []
        assert _consecutive_gaps({2027: 0, 2028: 0}) == [(2027, 2028)]
        assert _consecutive_gaps({2027: 0, 2028: 1, 2029: 0}) == []


class TestOwnershipReachesTheEngine:
    def test_the_builder_attaches_holdings_and_the_engine_certifies(
        self, db: Session, cap_params, seeded_league: dict
    ):
        team_a, team_b = seeded_league["team_a"], seeded_league["team_b"]
        for year in (2028, 2029, 2030, 2031):
            db.add(
                DraftPick(
                    original_team_id=team_b.id,
                    owning_team_id=team_a.id,
                    draft_year=year,
                    round_number=1,
                    is_verified=True,
                    conveyance="unconditional",
                    source_provider="test_fixture",
                )
            )
        db.commit()
        context = build_trade_context(
            db,
            [team_a.id, team_b.id],
            [],
            [
                {
                    "from_team_id": team_a.id,
                    "to_team_id": team_b.id,
                    "draft_year": 2029,
                    "round_number": 1,
                    "protections": None,
                    "is_hypothetical": True,
                }
            ],
        )
        assert context.team(team_a.id).first_round_holdings == {
            2028: 2,
            2029: 2,
            2030: 2,
            2031: 2,
        }
        results = TradeLegalityEngine().evaluate(context)["rule_results"]
        stepien = [r for r in results if r["rule_code"] == "STEPIEN_FUTURE_FIRSTS"]
        assert stepien and stepien[0]["status"] == "pass"
        assert stepien[0]["confidence"] == "high"

    def test_with_no_rows_the_rule_still_reports_unavailable(
        self, db: Session, cap_params, seeded_league: dict
    ):
        team_a, team_b = seeded_league["team_a"], seeded_league["team_b"]
        context = build_trade_context(
            db,
            [team_a.id, team_b.id],
            [],
            [
                {
                    "from_team_id": team_a.id,
                    "to_team_id": team_b.id,
                    "draft_year": 2029,
                    "round_number": 1,
                    "protections": None,
                    "is_hypothetical": True,
                }
            ],
        )
        assert context.team(team_a.id).first_round_holdings is None
        results = TradeLegalityEngine().evaluate(context)["rule_results"]
        stepien = [r for r in results if r["rule_code"] == "STEPIEN_FUTURE_FIRSTS"]
        assert stepien and stepien[0]["status"] == "unavailable"
