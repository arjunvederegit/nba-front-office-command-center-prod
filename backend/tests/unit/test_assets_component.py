"""R5-1c. `assets` stops being a placebo.

Measured before this change, over 482 scored evaluations of the post-R4 engine on the 30
ingested rosters: the component took exactly **three values — {48, 50, 52}** — with sd
1.16 and a share of composite variance of **−0.006**, while holding 15 % of the weight.
Both of its informative inputs were structurally unavailable:

- picks were **counted**, 8 points each, so a 2027 unprotected first and a 2031 second
  were interchangeable — and no pick moved in the sample at all;
- payroll came from `payroll_after − payroll_before`, which are `None` unless *every*
  rostered player is priced. That is 0 of 30 teams under the available contract data.

The tests below pin the two fixes and, more importantly, the refusals that come with them.
"""

import pytest
from sqlalchemy.orm import Session

from app.analytics.picks import REFERENCE_SLOT, relative_pick_value
from app.db.models import DraftPick, Standing
from app.services.evaluation import (
    PICK_POINTS_PER_REFERENCE,
    REFERENCE_PICK_VALUE,
    EvaluationService,
)


def _pick(from_team: str, to_team: str, year: int, round_number: int = 1, **kw) -> dict:
    return {
        "from_team_id": from_team,
        "to_team_id": to_team,
        "draft_year": year,
        "round_number": round_number,
        "protections": kw.get("protections"),
        "is_hypothetical": kw.get("is_hypothetical", True),
    }


@pytest.fixture()
def service(db: Session, seeded_league: dict) -> EvaluationService:
    for team, win_pct in ((seeded_league["team_a"], 0.600), (seeded_league["team_b"], 0.300)):
        db.add(
            Standing(
                team_id=team.id,
                season="2025-26",
                wins=int(82 * win_pct),
                losses=82 - int(82 * win_pct),
                win_pct=win_pct,
            )
        )
    db.commit()
    return EvaluationService(db)


class TestTheAnchorIsUnchanged:
    def test_a_reference_pick_is_still_worth_eight_points(self):
        """R4 valued every pick at 8 composite points. R5 keeps that for the reference
        asset — a mid-first-rounder — and prices everything else relative to it. No scale
        constant moves; only the relative pricing appears."""
        assert PICK_POINTS_PER_REFERENCE == 8.0
        assert pytest.approx(relative_pick_value(REFERENCE_SLOT)) == REFERENCE_PICK_VALUE

    def test_a_top_pick_is_worth_more_than_a_late_second(self):
        assert relative_pick_value(1) / REFERENCE_PICK_VALUE > 2.0
        assert relative_pick_value(55) / REFERENCE_PICK_VALUE < 0.3


class TestPicksAreValuedNotCounted:
    def test_acquiring_a_verified_pick_scores_above_neutral(
        self, db: Session, seeded_league: dict, service: EvaluationService
    ):
        a, b = seeded_league["team_a"], seeded_league["team_b"]
        db.add(
            DraftPick(
                original_team_id=b.id,
                owning_team_id=b.id,
                draft_year=2029,
                round_number=1,
                is_verified=True,
                conveyance="unconditional",
                source_provider="test_fixture",
            )
        )
        db.commit()
        score, detail = service._assets(a.id, [_pick(b.id, a.id, 2029)], None, False, 0)
        assert score is not None and score > 50.0
        assert len(detail["picks_priced"]) == 1
        assert detail["picks_priced"][0]["precision"] == "interval"

    def test_two_picks_from_different_teams_are_not_interchangeable(
        self, db: Session, seeded_league: dict, service: EvaluationService
    ):
        """The defect the flat 8 points hid. Team B finished 0.300 and Team A 0.600, so
        B's own first lands far earlier and is worth materially more."""
        a, b = seeded_league["team_a"], seeded_league["team_b"]
        for owner, year in ((a, 2029), (b, 2029)):
            db.add(
                DraftPick(
                    original_team_id=owner.id,
                    owning_team_id=owner.id,
                    draft_year=year,
                    round_number=1,
                    is_verified=True,
                    conveyance="unconditional",
                    source_provider="test_fixture",
                )
            )
        db.commit()
        from_bad_team, _ = service._assets(a.id, [_pick(b.id, a.id, 2029)], None, False, 0)
        # A pick the focal team already owns, coming back to it, prices off its own record.
        from_good_team, _ = service._assets(b.id, [_pick(a.id, b.id, 2029)], None, False, 0)
        assert from_bad_team != from_good_team

    def test_a_second_rounder_moves_the_score_less_than_a_first(
        self, db: Session, seeded_league: dict, service: EvaluationService
    ):
        a, b = seeded_league["team_a"], seeded_league["team_b"]
        for round_number in (1, 2):
            db.add(
                DraftPick(
                    original_team_id=b.id,
                    owning_team_id=b.id,
                    draft_year=2029,
                    round_number=round_number,
                    is_verified=True,
                    conveyance="unconditional",
                    source_provider="test_fixture",
                )
            )
        db.commit()
        first, _ = service._assets(a.id, [_pick(b.id, a.id, 2029, 1)], None, False, 0)
        second, _ = service._assets(a.id, [_pick(b.id, a.id, 2029, 2)], None, False, 0)
        assert first is not None and second is not None
        assert first > second > 50.0


class TestRefusals:
    def test_an_unverified_pick_is_not_scored(
        self, db: Session, seeded_league: dict, service: EvaluationService
    ):
        """No ownership row at all: the pick is described, listed with the range it would
        have spanned, and left out of the score."""
        a, b = seeded_league["team_a"], seeded_league["team_b"]
        score, detail = service._assets(a.id, [_pick(b.id, a.id, 2029)], None, False, 0)
        assert detail["picks_priced"] == []
        assert len(detail["picks_not_priced"]) == 1
        assert detail["picks_not_priced"][0]["precision"] == "unknown"
        assert score is None
        assert "no draft pick in this deal could be priced" in detail["unavailable"]

    def test_a_swapped_pick_is_not_midpointed_into_the_score(
        self, db: Session, seeded_league: dict, service: EvaluationService
    ):
        a, b = seeded_league["team_a"], seeded_league["team_b"]
        db.add(
            DraftPick(
                original_team_id=b.id,
                owning_team_id=b.id,
                draft_year=2029,
                round_number=1,
                is_verified=False,
                conveyance="swap",
                protections="more favorable of the two",
                source_provider="test_fixture",
            )
        )
        db.commit()
        score, detail = service._assets(
            a.id, [_pick(b.id, a.id, 2029)], -5_000_000, True, 0
        )
        assert detail["picks_priced"] == []
        assert detail["picks_not_priced"][0]["precision"] in ("range", "unknown")
        # Nothing else can carry the component, so it is withheld rather than midpointed.
        assert score is None

    def test_the_component_is_withheld_on_a_player_only_trade(
        self, db: Session, seeded_league: dict, service: EvaluationService
    ):
        """The placebo fix. With no priceable pick, what remains is a roster-spot term
        spanning four points, which cannot express asset value."""
        a = seeded_league["team_a"]
        score, detail = service._assets(a.id, [], None, False, 1)
        assert score is None
        assert "roster-spot term" in detail["unavailable"]

    def test_a_payroll_change_alone_does_not_score_this_component(
        self, db: Session, seeded_league: dict, service: EvaluationService
    ):
        """Measured and rejected. A first pass scored the payroll delta here; over the
        resulting 168 fully-scored evaluations `assets` correlated 0.837 with `contract`
        (0.779 Spearman), because with no pick moving both reduce to the same salary
        delta. It is reported instead — `contract` is the component that owns salary."""
        a = seeded_league["team_a"]
        score, detail = service._assets(a.id, [], 20_000_000, True, 0)
        assert score is None
        assert detail["payroll_delta"] == 20_000_000
        assert detail["payroll_scored"] is False
        assert "0.837 correlated" in detail["payroll_scored_note"]
        assert "sum of the moved players' salaries" in detail["payroll_basis"]

    def test_the_payroll_delta_never_changes_the_score(
        self, db: Session, seeded_league: dict, service: EvaluationService
    ):
        """The structural guarantee behind the note above."""
        a, b = seeded_league["team_a"], seeded_league["team_b"]
        db.add(
            DraftPick(
                original_team_id=b.id,
                owning_team_id=b.id,
                draft_year=2029,
                round_number=1,
                is_verified=True,
                conveyance="unconditional",
                source_provider="test_fixture",
            )
        )
        db.commit()
        moves = [_pick(b.id, a.id, 2029)]
        taking_on, _ = service._assets(a.id, moves, 40_000_000, True, 0)
        shedding, _ = service._assets(a.id, moves, -40_000_000, True, 0)
        assert taking_on == shedding


class TestPayrollDeltaComesFromTheMovedPlayers:
    def test_it_is_exact_when_every_moved_player_is_priced(
        self, db: Session, seeded_league: dict
    ):
        """The structural fix: the delta needs the players in the deal, not two entire
        priced rosters. `payroll_before`/`payroll_after` require the latter and are `None`
        for 30 of 30 teams under the available contract data."""
        from tests.unit.test_evaluation_sanity import _evaluate, _moves

        moves = _moves(
            seeded_league["roster_a"][:1], seeded_league["team_a"], seeded_league["team_b"]
        ) + _moves(
            seeded_league["roster_b"][:1], seeded_league["team_b"], seeded_league["team_a"]
        )
        result = _evaluate(db, seeded_league, seeded_league["team_a"], moves)
        assets = result["detail"]["assets"]
        assert result["legality"].get("payroll_before") is None, (
            "the fixture deliberately mirrors production, where no team is fully priced"
        )
        assert assets.get("payroll_delta") is not None, (
            "...and the delta is still computable from the two moved players"
        )

    def test_an_unpriced_player_withholds_the_delta_rather_than_guessing(
        self, db: Session, seeded_league: dict
    ):
        from tests.unit.test_evaluation_sanity import _evaluate, _moves

        moves = _moves(
            [seeded_league["no_contract_a"]], seeded_league["team_a"], seeded_league["team_b"]
        )
        result = _evaluate(db, seeded_league, seeded_league["team_a"], moves)
        assets = result["detail"]["assets"]
        assert "payroll_delta" not in assets
        assert "no salary for the cap league year" in assets["payroll_note"]
