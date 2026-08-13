"""R5.5. The one-way `fit` baseline that R1 deferred and R5 deferred again.

R1 found `fit_score` substituting a flat 50th-percentile player for a missing side, so
trading everyone away for nothing scored as if a median NBA rotation player had been
acquired in every skill. It removed the constant and withheld the component. R5 recorded
that it would supply a measured baseline and did not, on the grounds that it changes a
scored component and no measurement had been taken.

The measurement is `REPLACEMENT_SKILLS` (see `analytics/archetypes.py`), taken on the same
population `REPLACEMENT_TEI` is fitted on. The two sides get different baselines because
the allocator's two directions differ:

    nothing arriving   his minutes are played by a replacement -> REPLACEMENT_SKILLS
    nothing departing  his minutes come out of the incumbents  -> the roster's own profile

These tests pin that the substitution happens, is disclosed, is not flat, and — the point
of the whole exercise — does not touch a two-sided deal.
"""

import numpy as np
import pytest

from app.analytics.archetypes import REPLACEMENT_SKILLS, SKILL_KEYS
from app.services.evaluation import EvaluationService, PlayerCard


def _card(pid, name, skills, minutes=24.0, tei=0.5):
    return PlayerCard(
        player_id=pid,
        name=name,
        tei=tei,
        tei_sigma=1.0,
        availability=0.8,
        minutes=minutes,
        age=27.0,
        skills=skills,
    )


def _skills(value):
    return dict.fromkeys(SKILL_KEYS, value)


@pytest.fixture
def service(db):
    svc = EvaluationService(db)
    svc._needs_cache["T"] = {"rim_protection": 0.9, "rebounding": 0.6, "scoring": 0.8}
    return svc


@pytest.fixture
def roster():
    return [
        _card(f"r{i}", f"R{i}", _skills(0.5 + 0.02 * i), minutes=30.0 - 2.0 * i) for i in range(10)
    ]


class TestTheMeasuredProfile:
    def test_the_profile_covers_every_skill(self):
        assert set(REPLACEMENT_SKILLS) == set(SKILL_KEYS)

    def test_the_profile_is_not_the_flat_constant_r1_removed(self):
        """The shape is the finding. A flat 0.5 — or a flat anything — erases it."""
        values = np.array(list(REPLACEMENT_SKILLS.values()))
        assert values.std() > 0.03, "a flat profile is the constant R1 already removed"
        assert not np.allclose(values, 0.5)

    def test_a_replacement_player_cannot_score_or_create(self):
        """The measured separation: scoring -5.99 t, creation -3.97, against
        rebounding +1.36 and team_defense +1.01, which are not separated from median."""
        assert REPLACEMENT_SKILLS["scoring"] < 0.42
        assert REPLACEMENT_SKILLS["creation"] < 0.45
        assert REPLACEMENT_SKILLS["rebounding"] > 0.50
        assert REPLACEMENT_SKILLS["team_defense"] > 0.50

    def test_every_value_is_a_percentile(self):
        assert all(0.0 <= v <= 1.0 for v in REPLACEMENT_SKILLS.values())


class TestOneWayOut:
    def test_giving_a_player_away_for_nothing_is_now_scored(self, service, roster):
        leaving = _card("x", "X", _skills(0.85), minutes=32.0)
        score, detail = service._fit("T", roster, [], [leaving])
        assert score is not None
        assert detail["baseline_used"] == "replacement"
        assert "replacement" in detail["baseline_note"]

    def test_giving_away_a_good_player_scores_below_neutral(self, service, roster):
        leaving = _card("x", "X", _skills(0.9), minutes=32.0)
        score, _ = service._fit("T", roster, [], [leaving])
        assert score < 50.0

    def test_giving_away_a_replacement_level_player_is_near_neutral(self, service, roster):
        """The baseline's own definition: losing a player who IS a replacement player
        changes nothing, because a replacement replaces him."""
        leaving = _card("x", "X", dict(REPLACEMENT_SKILLS), minutes=12.0)
        score, detail = service._fit("T", roster, [], [leaving])
        assert detail["raw_fit"] == pytest.approx(0.0, abs=1e-9)
        assert score == pytest.approx(50.0, abs=1e-6)

    def test_giving_away_a_better_player_scores_worse_than_a_worse_one(self, service, roster):
        good, poor = _card("g", "G", _skills(0.9)), _card("p", "P", _skills(0.55))
        s_good, _ = service._fit("T", roster, [], [good])
        s_poor, _ = service._fit("T", roster, [], [poor])
        assert s_good < s_poor

    def test_shedding_a_below_replacement_player_can_help(self, service, roster):
        poor = _card("p", "P", _skills(0.15), minutes=18.0)
        score, _ = service._fit("T", roster, [], [poor])
        assert score > 50.0


class TestOneWayIn:
    def test_taking_a_player_for_nothing_is_scored_against_the_roster(self, service, roster):
        arriving = _card("x", "X", _skills(0.9), minutes=30.0)
        score, detail = service._fit("T", roster, [arriving], [])
        assert score is not None
        assert detail["baseline_used"] == "roster"
        assert "roster's own" in detail["baseline_note"]

    def test_taking_a_good_player_for_nothing_scores_above_neutral(self, service, roster):
        arriving = _card("x", "X", _skills(0.95), minutes=30.0)
        score, _ = service._fit("T", roster, [arriving], [])
        assert score > 50.0

    def test_the_baseline_is_the_rosters_own_profile_not_a_constant(self, service):
        """Two rosters of different quality must price the same arrival differently."""
        weak = [_card(f"w{i}", f"W{i}", _skills(0.25), minutes=24.0) for i in range(10)]
        strong = [_card(f"s{i}", f"S{i}", _skills(0.85), minutes=24.0) for i in range(10)]
        arriving = _card("x", "X", _skills(0.6), minutes=28.0)
        s_weak, _ = service._fit("T", weak, [arriving], [])
        s_strong, _ = service._fit("T", strong, [arriving], [])
        assert s_weak > s_strong

    def test_the_roster_profile_is_minutes_weighted(self, service):
        """A starter's skills displace more than a reserve's."""
        mixed = [
            _card("big", "Big", _skills(0.9), minutes=36.0),
            _card("small", "Small", _skills(0.1), minutes=4.0),
        ]
        profile = service._roster_skill_profile(mixed, exclude=set())
        assert profile["scoring"] == pytest.approx((0.9 * 36 + 0.1 * 4) / 40.0)


class TestTwoSidedDealsAreUntouched:
    def test_a_two_sided_deal_names_no_baseline(self, service, roster):
        inn = _card("i", "I", _skills(0.7), minutes=28.0)
        out = _card("o", "O", _skills(0.4), minutes=26.0)
        score, detail = service._fit("T", roster, [inn], [out])
        assert detail["baseline_used"] is None
        assert "baseline_note" not in detail

    def test_the_two_sided_score_does_not_move(self, service, roster):
        """Measured on 240 two-sided deals: baseline `None` on all 240. This pins the
        arithmetic rather than the sample."""
        inn = _card("i", "I", _skills(0.7), minutes=28.0)
        out = _card("o", "O", _skills(0.4), minutes=26.0)
        _, detail = service._fit("T", roster, [inn], [out])
        # (0.7 - 0.4) on each skill the needs claim, unchanged by anything R5.5 added.
        assert detail["skill_delta"]["rim_protection"] == pytest.approx(0.3)


class TestWithholdingStillHappens:
    def test_a_deal_with_nothing_on_either_side_is_withheld(self, service, roster):
        score, detail = service._fit("T", roster, [], [])
        assert score is None
        assert "neither side" in detail["unavailable"]

    def test_an_arrival_against_an_unmeasurable_roster_is_withheld(self, service):
        blank = [_card("b", "B", {}, minutes=None)]
        arriving = _card("x", "X", _skills(0.8), minutes=30.0)
        score, detail = service._fit("T", blank, [arriving], [])
        assert score is None
        assert "no rostered player" in detail["unavailable"]

    def test_needs_are_still_required(self, service, roster):
        service._needs_cache["EMPTY"] = {}
        score, detail = service._fit("EMPTY", roster, [], [roster[0]])
        assert score is None
        assert "team needs" in detail["unavailable"]
