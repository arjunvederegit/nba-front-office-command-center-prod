"""R4-1a — roster fit sums over SKILLS, not over needs.

Several needs legitimately resolve to one skill. The pre-R4 loop ran over needs, so one
skill delta was multiplied by two or three severities and added that many times. Measured
on the 30 seeded teams: 19 of 30 had at least one skill claimed by two or more active
needs; inflation averaged 1.625x and peaked at 2.67x.

These are regression tests (the specific defect must not return) plus property tests (the
invariant must hold for any need set, not just the ones that were measured).
"""

import itertools

import pytest

from app.analytics.fit import GAMMA, fit_score


def _score(needs, need_to_skill, *, delta=0.4, strengths=None):
    """One incoming and one outgoing player differing by `delta` in every named skill."""
    skills = sorted(set(need_to_skill.values()))
    incoming = dict.fromkeys(skills, 0.5 + delta / 2)
    outgoing = dict.fromkeys(skills, 0.5 - delta / 2)
    return fit_score(
        needs=needs,
        incoming=[(incoming, 30.0)],
        outgoing=[(outgoing, 30.0)],
        roster_strengths=strengths or dict.fromkeys(skills, 0.5),
        need_to_skill=need_to_skill,
    )


class TestNoDoubleCount:
    def test_two_needs_on_one_skill_score_once(self):
        """The exact defect: `playmaking` and `secondary_creation` both mean creation."""
        mapping = {"playmaking": "creation", "secondary_creation": "creation"}
        both, detail = _score({"playmaking": 0.8, "secondary_creation": 0.6}, mapping)
        only_one, _ = _score({"playmaking": 0.8}, mapping)

        # Before R4-1a this was 0.8*0.4 + 0.6*0.4 = 0.56, i.e. 1.75x the correct 0.32.
        assert both == pytest.approx(only_one)
        assert both == pytest.approx(0.8 * 0.4)
        assert detail["skill_severity_applied"]["creation"] == pytest.approx(0.8)
        assert detail["needs_sharing_a_skill"] == {
            "creation": ["playmaking", "secondary_creation"]
        }

    def test_three_needs_on_one_skill_score_once(self):
        """The measured worst case — 2.67x inflation on a real seeded team."""
        mapping = {
            "playmaking": "creation",
            "ball_security": "creation",
            "secondary_creation": "creation",
        }
        score, detail = _score(
            {"playmaking": 0.8, "ball_security": 0.733, "secondary_creation": 0.6}, mapping
        )
        assert score == pytest.approx(0.8 * 0.4)
        assert len(detail["needs_sharing_a_skill"]["creation"]) == 3

    def test_severity_is_the_max_not_the_sum(self):
        mapping = {"a": "creation", "b": "creation"}
        _, detail = _score({"a": 0.3, "b": 0.9}, mapping)
        assert detail["skill_severity_applied"]["creation"] == pytest.approx(0.9)

    def test_distinct_skills_still_add(self):
        """The fix must not collapse genuinely different skills."""
        mapping = {"playmaking": "creation", "rim_protection": "rim_protection"}
        score, _ = _score({"playmaking": 0.8, "rim_protection": 0.5}, mapping)
        assert score == pytest.approx(0.8 * 0.4 + 0.5 * 0.4)


class TestAttributionReconciles:
    """The UI lists a number per NEED. Those numbers must sum to the score."""

    def test_per_need_parts_sum_to_the_skill_contribution(self):
        mapping = {"playmaking": "creation", "secondary_creation": "creation"}
        score, detail = _score({"playmaking": 0.8, "secondary_creation": 0.6}, mapping)
        assert sum(detail["needs_addressed"].values()) == pytest.approx(score, abs=1e-3)

    def test_parts_are_proportional_to_severity(self):
        mapping = {"playmaking": "creation", "secondary_creation": "creation"}
        _, detail = _score({"playmaking": 0.8, "secondary_creation": 0.4}, mapping)
        a = detail["needs_addressed"]["playmaking"]
        b = detail["needs_addressed"]["secondary_creation"]
        assert a == pytest.approx(2 * b, rel=1e-3)

    def test_every_addressed_need_is_still_reported(self):
        """Counting a skill once must not make a need disappear from the explanation."""
        mapping = {"playmaking": "creation", "secondary_creation": "creation"}
        _, detail = _score({"playmaking": 0.8, "secondary_creation": 0.6}, mapping)
        assert set(detail["needs_addressed"]) == {"playmaking", "secondary_creation"}

    def test_zero_severity_needs_do_not_divide_by_zero(self):
        mapping = {"a": "creation", "b": "creation"}
        score, detail = _score({"a": 0.0, "b": 0.0}, mapping)
        assert score == pytest.approx(0.0)
        assert all(v == pytest.approx(0.0) for v in detail["needs_addressed"].values())


class TestProperties:
    """Invariants that must hold for any need set, not only the measured ones."""

    SKILLS = ["creation", "shooting", "rim_protection"]

    @pytest.mark.parametrize(
        "severities",
        list(itertools.product([0.0, 0.25, 0.6, 1.0], repeat=3)),
    )
    def test_score_never_exceeds_the_single_counted_bound(self, severities):
        """With every need pointing at one skill, the score can never exceed
        max(severity) * delta — the definition of not double-counting."""
        mapping = {f"n{i}": "creation" for i in range(3)}
        needs = {f"n{i}": s for i, s in enumerate(severities)}
        score, _ = _score(needs, mapping, strengths={"creation": 0.5})
        assert score <= max(severities) * 0.4 + 1e-9

    @pytest.mark.parametrize("n_needs", [1, 2, 3, 4, 5])
    def test_adding_a_less_severe_duplicate_need_never_changes_the_score(self, n_needs):
        """Monotone in the right way: piling on more needs for the same skill must not
        inflate the score, because the roster's deficiency has not changed."""
        mapping = {f"n{i}": "creation" for i in range(n_needs)}
        needs = {"n0": 0.9, **{f"n{i}": 0.2 for i in range(1, n_needs)}}
        score, _ = _score(needs, mapping)
        assert score == pytest.approx(0.9 * 0.4)

    def test_a_turnover_need_never_rewards_a_worse_delta(self):
        """Sign sanity: a negative skill delta must produce a negative contribution
        regardless of how many needs share the skill."""
        mapping = {"a": "creation", "b": "creation"}
        score, _ = _score({"a": 0.8, "b": 0.5}, mapping, delta=-0.4)
        assert score < 0

    def test_redundancy_is_unaffected_by_need_grouping(self):
        """Redundancy already iterated over skills; grouping needs must not touch it."""
        mapping = {"a": "creation", "b": "creation"}
        _, one = _score({"a": 0.8}, mapping, strengths={"creation": 0.9})
        _, two = _score({"a": 0.8, "b": 0.5}, mapping, strengths={"creation": 0.9})
        assert one["redundancies"] == two["redundancies"]
        assert one["gamma"] == GAMMA


class TestUnmappedAndUnmeasured:
    def test_a_need_with_no_skill_is_ignored_not_defaulted(self):
        score, detail = _score({"mystery_need": 0.9}, {"playmaking": "creation"})
        assert score == pytest.approx(0.0)
        assert detail["needs_addressed"] == {}

    def test_a_skill_measured_on_one_side_only_is_not_scored(self):
        score, detail = fit_score(
            needs={"playmaking": 0.9},
            incoming=[({"creation": 0.9, "size": 0.8}, 30.0)],
            outgoing=[({"creation": 0.5}, 30.0)],
            roster_strengths={"creation": 0.5, "size": 0.5},
            need_to_skill={"playmaking": "creation", "lineup_size": "size"},
        )
        assert detail["skills_not_compared"] == ["size"]
        assert score == pytest.approx(0.9 * 0.4)

    def test_empty_needs_produce_no_severity_map(self):
        _, detail = _score({}, {"playmaking": "creation"})
        assert detail["skill_severity_applied"] == {}
        assert detail["needs_sharing_a_skill"] == {}
