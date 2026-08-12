"""R5-1b. `risk` must not restate `performance`.

Until R5 the dominant risk term was `prob_positive` — the Monte Carlo's probability that
Δwins > 0, which is the performance component expressed as a probability. Measured over
482 scored evaluations of the post-R4 engine on the 30 ingested rosters:

    corr(prob_positive, performance)    0.913
    corr(risk, performance)             0.851 Pearson / 0.937 Spearman
    risk's share of composite variance  0.244

A quarter of the composite's variance came from a component that was 85–94 % another
component, so `performance` carried roughly double the weight the vector declared.

These tests pin the fix at the level of the mechanism — the score cannot depend on the
outcome distribution at all — rather than at the level of a correlation threshold, which
a future change could satisfy while restoring the double count by another route.
"""

import numpy as np
import pytest
from sqlalchemy.orm import Session

from app.services.evaluation import EvaluationService, PlayerCard


def _card(pid: str, availability: float | None, minutes: float | None = 24.0) -> PlayerCard:
    return PlayerCard(
        player_id=pid,
        name=pid.upper(),
        tei=1.0,
        tei_sigma=0.5,
        availability=availability,
        minutes=minutes,
        age=27.0,
        skills={},
    )


def _service(db: Session) -> EvaluationService:
    return EvaluationService(db)


EMPTY_LEGALITY: dict = {"rule_results": [], "teams": {}, "overall_status": "conditionally_valid"}


class TestRiskIgnoresTheOutcomeDistribution:
    def test_the_signature_no_longer_accepts_uncertainty(self, db: Session):
        """The structural guarantee: risk cannot read the Monte Carlo, because it is not
        handed it. A correlation test alone would let a future edit pass one in again."""
        import inspect

        params = set(inspect.signature(EvaluationService._risk).parameters)
        assert "uncertainty" not in params
        assert {"roster", "incoming", "outgoing", "legality"} <= params

    def test_no_risk_source_line_mentions_prob_positive(self):
        import inspect

        from app.services import evaluation

        source = inspect.getsource(evaluation.EvaluationService._risk)
        body = "\n".join(
            line for line in source.splitlines() if not line.strip().startswith("#")
        )
        # The docstring names it while explaining the removal; no executable line may.
        code = body.split('"""')[-1]
        assert "prob_positive" not in code

    def test_prob_positive_is_still_published(self, db: Session, seeded_league: dict):
        """Removing it from the score must not remove it from the response."""
        from tests.unit.test_evaluation_sanity import _evaluate, _moves

        moves = _moves(
            seeded_league["roster_a"][:1], seeded_league["team_a"], seeded_league["team_b"]
        ) + _moves(
            seeded_league["roster_b"][:1], seeded_league["team_b"], seeded_league["team_a"]
        )
        result = _evaluate(db, seeded_league, seeded_league["team_a"], moves)
        assert result["uncertainty"]["prob_positive"] is not None


class TestAvailabilityExposure:
    def test_a_neutral_swap_scores_neutral(self, db: Session):
        service = _service(db)
        roster = [_card(f"r{i}", 0.8) for i in range(8)]
        score, detail = service._risk(
            roster, [_card("in", 0.8)], [_card("out", 0.8)], EMPTY_LEGALITY, "T"
        )
        assert score == pytest.approx(50.0)
        assert detail["availability_delta"] == pytest.approx(0.0)

    def test_acquiring_the_more_durable_side_scores_above_neutral(self, db: Session):
        service = _service(db)
        roster = [_card(f"r{i}", 0.8) for i in range(8)]
        score, _ = service._risk(
            roster, [_card("in", 0.95)], [_card("out", 0.55)], EMPTY_LEGALITY, "T"
        )
        assert score == pytest.approx(50.0 + 0.40 * 50.0)

    def test_it_is_the_change_not_the_level(self, db: Session):
        """Two deals where the incoming package has identical availability but the
        departing one does not must not score the same. The old component could not tell
        them apart, because it only looked at the incoming side."""
        service = _service(db)
        roster = [_card(f"r{i}", 0.8) for i in range(8)]
        shedding_fragility, _ = service._risk(
            roster, [_card("in", 0.7)], [_card("out", 0.4)], EMPTY_LEGALITY, "T"
        )
        taking_on_fragility, _ = service._risk(
            roster, [_card("in", 0.7)], [_card("out", 0.95)], EMPTY_LEGALITY, "T"
        )
        assert shedding_fragility > 50.0 > taking_on_fragility

    def test_minutes_weight_the_average(self, db: Session):
        service = _service(db)
        roster = [_card(f"r{i}", 0.8) for i in range(8)]
        # A fragile 32-minute starter alongside a durable 4-minute reserve.
        heavy = [_card("starter", 0.5, 32.0), _card("reserve", 1.0, 4.0)]
        score, detail = service._risk(
            roster, heavy, [_card("out", 0.8, 36.0)], EMPTY_LEGALITY, "T"
        )
        expected_in = (0.5 * 32 + 1.0 * 4) / 36
        assert detail["incoming_availability"] == pytest.approx(round(expected_in, 3))
        assert score < 50.0

    def test_an_empty_side_is_priced_at_the_roster_it_leaves_behind(self, db: Session):
        """A one-way acquisition still has exposure: the arriving minutes displace the
        minutes the current roster would otherwise have played, and that roster's
        availability is measured, not assumed."""
        service = _service(db)
        roster = [_card(f"r{i}", 0.6) for i in range(8)]
        score, detail = service._risk(roster, [_card("in", 0.9)], [], EMPTY_LEGALITY, "T")
        assert detail["outgoing_availability"] is None, "no departing package was measured"
        assert detail["roster_availability"] == pytest.approx(0.6)
        assert "baseline_note" in detail
        assert score == pytest.approx(50.0 + (0.9 - 0.6) * 50.0)

    def test_it_is_withheld_when_nothing_at_all_is_measured(self, db: Session):
        service = _service(db)
        roster = [_card(f"r{i}", None) for i in range(8)]
        score, detail = service._risk(
            roster, [_card("in", None)], [_card("out", None)], EMPTY_LEGALITY, "T"
        )
        assert score is None
        assert "unavailable" in detail

    def test_the_scale_reaches_both_endpoints(self, db: Session):
        """Availability is a share of games, so its change is bounded on [-1, 1] and both
        ends mean something. This component is affine, not squashed."""
        service = _service(db)
        roster = [_card(f"r{i}", 0.8) for i in range(8)]
        best, _ = service._risk(
            roster, [_card("in", 1.0)], [_card("out", 0.0)], EMPTY_LEGALITY, "T"
        )
        worst, _ = service._risk(
            roster, [_card("in", 0.0)], [_card("out", 1.0)], EMPTY_LEGALITY, "T"
        )
        assert best == pytest.approx(100.0)
        assert worst == pytest.approx(0.0)


class TestLegalityVerificationIsReportedNotScored:
    def test_it_is_published_with_its_own_disclaimer(self, db: Session):
        service = _service(db)
        roster = [_card(f"r{i}", 0.8) for i in range(8)]
        legality = {
            "rule_results": [
                {"team_id": "T", "status": "unavailable"},
                {"team_id": "T", "status": "pass"},
                {"team_id": "OTHER", "status": "fail"},
            ]
        }
        _, detail = service._risk(
            roster, [_card("in", 0.8)], [_card("out", 0.8)], legality, "T"
        )
        block = detail["legality_verification"]
        assert block["rules_evaluated"] == 2, "another team's rules are not this team's"
        assert block["rules_with_a_definite_verdict"] == 1
        assert block["share"] == pytest.approx(0.5)
        assert block["scored"] is False

    def test_changing_it_does_not_change_the_score(self, db: Session):
        """The reason it is not scored: measured over 482 evaluations it runs
        0.063 ± 0.071 with a ceiling of 0.143, and what moves it is which contract fields
        the provider supplies — a property of the dataset, not of the deal."""
        service = _service(db)
        roster = [_card(f"r{i}", 0.8) for i in range(8)]
        nothing_verified = {"rule_results": [{"team_id": "T", "status": "unavailable"}] * 9}
        all_verified = {"rule_results": [{"team_id": "T", "status": "pass"}] * 9}
        a, _ = service._risk(
            roster, [_card("in", 0.9)], [_card("out", 0.6)], nothing_verified, "T"
        )
        b, _ = service._risk(
            roster, [_card("in", 0.9)], [_card("out", 0.6)], all_verified, "T"
        )
        assert a == b


class TestOrthogonalityOnRealRosters:
    """The measured claim, re-derived on the seeded league rather than asserted.

    Not a correlation threshold on the shipped sample — that would be a number to tune.
    The assertion is the qualitative one the redesign exists to establish: exposure varies
    for reasons the projection does not see.
    """

    def test_two_deals_with_the_same_projection_can_differ_on_risk(self, db: Session):
        service = _service(db)
        roster = [_card(f"r{i}", 0.8) for i in range(8)]
        # Identical TEI and minutes on both sides, so any performance model that reads
        # only impact and minutes returns the same answer for both.
        durable = _card("in_durable", 0.98)
        fragile = _card("in_fragile", 0.42)
        assert durable.tei == fragile.tei and durable.minutes == fragile.minutes
        a, _ = service._risk(roster, [durable], [_card("out", 0.8)], EMPTY_LEGALITY, "T")
        b, _ = service._risk(roster, [fragile], [_card("out", 0.8)], EMPTY_LEGALITY, "T")
        assert a - b == pytest.approx((0.98 - 0.42) * 50.0)

    def test_the_component_has_real_spread_across_plausible_packages(self, db: Session):
        service = _service(db)
        roster = [_card(f"r{i}", 0.8) for i in range(8)]
        rng = np.random.default_rng(20260812)
        scores = []
        for _ in range(200):
            a_in, a_out = rng.uniform(0.3, 1.0), rng.uniform(0.3, 1.0)
            score, _ = service._risk(
                roster, [_card("in", float(a_in))], [_card("out", float(a_out))],
                EMPTY_LEGALITY, "T",
            )
            scores.append(score)
        assert np.std(scores) > 5.0, "a component with no spread is a placebo"
