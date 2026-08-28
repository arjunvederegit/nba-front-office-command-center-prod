"""The domain layer is a vocabulary, and these tests pin the three properties that make it
one.

1. **It agrees with the code that already shipped.** Moving `SKILL_KEYS`, `ROLE_ID`,
   `NEED_TO_SKILL`, `UNADDRESSABLE_NEEDS` and the strategy weights into `app.domain` is a
   canonicalisation, not a rewrite. If any of them drifts from what `app.analytics` and
   `app.services` re-export, a persisted `role_id` changes meaning or a cached skill vector
   is served under the wrong contract.

2. **It stays a vocabulary.** No pandas, no SQLAlchemy, no FastAPI, no `app.analytics`.
   The moment the domain imports the layer above it, the dependency arrow that makes it
   testable without a database is gone.

3. **A move changes membership and nothing else.** `apply` must not reallocate minutes,
   reassign archetypes or check legality. That restraint is what lets the scenario layer
   compose transitions with recomputation instead of entangling them.
"""

import ast
import pathlib

import pytest

from app.domain import archetypes as d_arch
from app.domain import mandate as d_mandate
from app.domain import needs as d_needs
from app.domain import skills as d_skills
from app.domain.evidence import Confidence, Evidence, Measurement
from app.domain.moves import Move, MoveKind, PlayerMovement, ScenarioStep, apply, replay
from app.domain.roster import LeagueState, RosterSlot, RosterState

DOMAIN_DIR = pathlib.Path(__file__).resolve().parents[2] / "app" / "domain"


# --------------------------------------------------------------------------- agreement


class TestTheVocabularyIsOneVocabulary:
    """Domain and the modules that re-export it must not drift apart."""

    def test_skill_keys_match_what_analytics_serves(self):
        from app.analytics.archetypes import SKILL_KEYS

        assert SKILL_KEYS is d_skills.SKILL_KEYS

    def test_skill_key_order_is_unchanged(self):
        # `skill_schema_fingerprint()` hashes "|".join(SKILL_KEYS) to namespace the league
        # skill cache. Reordering silently serves the previous shape for the rest of a
        # six-hour TTL, with no error anywhere.
        assert d_skills.SKILL_KEYS == [
            "shooting_volume",
            "shooting_accuracy",
            "creation",
            "turnover_avoidance",
            "team_defense",
            "rim_protection",
            "rebounding",
            "size",
            "scoring",
        ]

    def test_every_measured_dimension_is_computed_and_vice_versa(self):
        assert set(d_skills.MEASURED_KEYS) == set(d_skills.SKILL_KEYS)

    def test_role_ids_match_what_analytics_serves(self):
        from app.analytics.archetypes import ROLE_ID

        assert ROLE_ID is d_arch.ROLE_ID

    def test_role_ids_are_the_frozen_append_only_map(self):
        # `player_archetypes.role_id` is persisted per player-season. Renumbering rewrites
        # the meaning of every historical row.
        assert d_arch.ROLE_ID["lead guard"] == 0
        assert d_arch.ROLE_ID["finishing big"] == 13
        assert d_arch.ROLE_ID[d_arch.UNCLASSIFIED_SIZE] == 90
        assert d_arch.ROLE_ID[d_arch.UNCLASSIFIED_STATS] == 91
        assert sorted(d_arch.ROLE_ID.values()) == [*range(14), 90, 91]

    def test_need_to_skill_matches_what_analytics_serves(self):
        from app.analytics.needs import NEED_TO_SKILL

        assert NEED_TO_SKILL is d_needs.NEED_TO_SKILL

    def test_unaddressable_needs_match_what_analytics_serves(self):
        from app.analytics.archetypes import UNADDRESSABLE_NEEDS

        assert UNADDRESSABLE_NEEDS is d_needs.UNADDRESSABLE_NEEDS

    def test_strategy_weights_match_what_the_evaluator_serves(self):
        from app.services.evaluation import COMPONENT_KEYS, DEFAULT_WEIGHTS

        assert DEFAULT_WEIGHTS is d_mandate.STRATEGY_WEIGHTS
        assert COMPONENT_KEYS is d_mandate.COMPONENT_KEYS

    def test_the_stat_rules_and_the_catalog_describe_the_same_needs(self):
        """Every need the percentile rules produce must have a domain definition.

        The two lists are built independently — `analytics.needs.STAT_RULES` from the
        columns it reads, `domain.needs.CATALOG` from the product's vocabulary — so this
        is a real check and not a tautology. `lineup_size` and `secondary_creation` come
        from roster composition rather than a stat rule, which is why the comparison is
        one-directional.
        """
        from app.analytics.needs import STAT_RULES

        rule_keys = {r[0] for r in STAT_RULES}
        undocumented = sorted(rule_keys - set(d_needs.NEED_KEYS))
        assert undocumented == [], f"needs computed but not defined: {undocumented}"

    def test_every_need_points_at_a_declared_skill(self):
        unknown = sorted(set(d_needs.NEED_TO_SKILL.values()) - set(d_skills.SKILL_KEYS))
        assert unknown == []

    def test_point_of_attack_defense_is_measured_but_unanswered(self):
        """The withdrawal R4-2 made must survive the move into the domain layer."""
        assert "point_of_attack_defense" in d_needs.NEED_KEYS
        assert "point_of_attack_defense" not in d_needs.NEED_TO_SKILL
        assert not d_needs.addressable("point_of_attack_defense")
        reason = d_needs.UNADDRESSABLE_NEEDS["point_of_attack_defense"]
        assert "no player skill claims to address this" in reason

    def test_strategy_enum_covers_every_weight_vector(self):
        assert {s.value for s in d_mandate.Strategy} == set(d_mandate.STRATEGY_WEIGHTS)


# ------------------------------------------------------------------------ independence


class TestTheDomainImportsNothingAboveIt:
    """The dependency arrow points one way, checked at the source level.

    An import test rather than a convention: the value of the domain layer is that a
    ingestion job, an engine and the API can all read the same vocabulary without dragging
    a database session in behind it.
    """

    FORBIDDEN = {
        "pandas",
        "numpy",
        "sqlalchemy",
        "fastapi",
        "pydantic",
        "app.analytics",
        "app.services",
        "app.db",
        "app.api",
        "app.cba",
        "app.ingestion",
        "app.integrations",
    }

    @pytest.mark.parametrize(
        "path", sorted(DOMAIN_DIR.glob("*.py")), ids=lambda p: p.name
    )
    def test_no_module_imports_from_a_higher_layer(self, path):
        tree = ast.parse(path.read_text())
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.add(node.module)

        offending = sorted(
            name
            for name in imported
            for bad in self.FORBIDDEN
            if name == bad or name.startswith(f"{bad}.")
        )
        assert offending == [], f"{path.name} imports from a higher layer: {offending}"


# ---------------------------------------------------------------------------- evidence


class TestTheEvidenceLadder:
    def test_an_unavailable_measurement_must_state_why(self):
        with pytest.raises(ValueError):
            Measurement.unavailable("")

    def test_an_unavailable_measurement_carries_no_value_and_no_rung(self):
        m = Measurement.unavailable("no contract provider is configured")
        assert m.value is None
        assert m.available is False
        assert m.evidence is None
        assert m.confidence is Confidence.UNAVAILABLE
        assert "no contract provider" in m.reason

    def test_the_serialized_shape_always_carries_both_keys(self):
        """A client must never have to branch on key existence to find out if it has a
        number."""
        for m in (
            Measurement.observed(12.0, source="NBA.com"),
            Measurement.unavailable("not established"),
        ):
            d = m.as_dict()
            assert set(d) >= {"value", "available", "evidence", "confidence", "reason"}

    def test_the_three_rungs_are_distinct_and_self_describing(self):
        assert len({e.value for e in Evidence}) == 3
        for rung in Evidence:
            assert rung.definition
            assert rung.label

    def test_an_available_skill_states_a_method_and_an_unavailable_one_states_why(self):
        for dim in d_skills.DECLARED_DIMENSIONS:
            if dim.available:
                assert dim.method, f"{dim.key} is available but states no method"
                assert not dim.unavailable_reason
            else:
                assert dim.unavailable_reason, f"{dim.key} is unavailable but states no reason"

    def test_the_withdrawn_dimension_is_declared_unavailable_not_omitted(self):
        """Pivot names what it cannot see rather than leaving a silent hole."""
        poa = d_skills.BY_KEY["point_of_attack_defense"]
        assert poa.available is False
        assert "WITHDRAWN" in poa.unavailable_reason

    def test_defensive_composites_are_labelled_heuristic_not_validated(self):
        """Nothing in this repository validates a defensive metric non-circularly, and the
        vocabulary has to say so."""
        for key in ("team_defense", "rim_protection"):
            assert d_skills.BY_KEY[key].confidence is Confidence.HEURISTIC
            assert d_skills.BY_KEY[key].limitations


# -------------------------------------------------------------------------- archetypes


class TestArchetypes:
    def test_every_persisted_role_has_a_product_definition(self):
        assert set(d_arch.ROLE_ID) == set(d_arch.BY_KEY)

    def test_the_shipped_engine_produces_exactly_one_membership(self):
        """Faithful to what the deterministic chain actually does.

        The list shape exists so callers are already written against the plural form when
        R10 makes it plural — not because a multi-label engine exists today.
        """
        memberships = d_arch.single_membership("3&D wing")
        assert len(memberships) == 1
        assert memberships[0].primary is True
        assert memberships[0].weight == 1.0

    def test_a_membership_is_an_inference_and_never_claims_validation(self):
        m = d_arch.single_membership("stretch big")[0]
        assert m.evidence is Evidence.INFERRED
        assert m.confidence is not Confidence.VALIDATED

    def test_no_membership_is_produced_for_an_empty_label(self):
        assert d_arch.single_membership("") == []

    def test_unclassified_labels_are_recognised_as_such(self):
        m = d_arch.single_membership(d_arch.UNCLASSIFIED_SIZE)[0]
        assert m.unclassified is True


# ------------------------------------------------------------------ roster and moves


def _slot(pid: str, minutes: float | None = 24.0, tei: float | None = 0.5) -> RosterSlot:
    return RosterSlot(player_id=pid, player_name=pid.upper(), minutes=minutes, tei=tei)


def _state(team: str, ids: list[str]) -> RosterState:
    return RosterState(team_id=team, season="2025-26", slots=tuple(_slot(i) for i in ids))


class TestRosterState:
    def test_a_state_is_immutable_and_transitions_return_new_objects(self):
        before = _state("A", ["p1", "p2"])
        after = before.with_added(_slot("p3"))
        assert before.player_ids == {"p1", "p2"}
        assert after.player_ids == {"p1", "p2", "p3"}

    def test_adding_a_player_already_present_is_an_error(self):
        with pytest.raises(ValueError):
            _state("A", ["p1"]).with_added(_slot("p1"))

    def test_removing_a_player_who_is_absent_is_an_error(self):
        with pytest.raises(ValueError):
            _state("A", ["p1"]).with_removed("p9")

    def test_a_player_without_an_impact_estimate_is_named_not_dropped(self):
        """The adversarial battery's treatment, expressed in the state object.

        A missing TEI is an absence, never a zero, and the player still occupies a roster
        spot.
        """
        state = RosterState(
            team_id="A",
            season="2025-26",
            slots=(_slot("p1"), _slot("p2", tei=None)),
        )
        assert len(state) == 2
        unmodelled = state.players_without_impact_estimate
        assert [s.player_id for s in unmodelled] == ["p2"]
        assert unmodelled[0].tei is None


class TestMovesChangeMembershipAndNothingElse:
    def test_a_trade_moves_players_between_rosters(self):
        league = LeagueState.of("2025-26", [_state("A", ["a1", "a2"]), _state("B", ["b1"])])
        move = Move.trade(
            (
                PlayerMovement("a1", "A", "B", _slot("a1")),
                PlayerMovement("b1", "B", "A", _slot("b1")),
            )
        )
        after = apply(league, move)
        assert after.team("A").player_ids == {"a2", "b1"}
        assert after.team("B").player_ids == {"a1"}

    def test_apply_does_not_mutate_the_state_it_is_given(self):
        league = LeagueState.of("2025-26", [_state("A", ["a1"]), _state("B", [])])
        apply(league, Move.trade((PlayerMovement("a1", "A", "B", _slot("a1")),)))
        assert league.team("A").player_ids == {"a1"}
        assert league.team("B").player_ids == set()

    def test_applying_the_same_move_twice_gives_equal_results(self):
        """Purity is what makes a branch a second call rather than a rollback."""
        league = LeagueState.of("2025-26", [_state("A", ["a1"]), _state("B", [])])
        move = Move.trade((PlayerMovement("a1", "A", "B", _slot("a1")),))
        assert apply(league, move) == apply(league, move)

    def test_a_three_team_trade_never_requires_a_player_on_two_rosters_at_once(self):
        league = LeagueState.of(
            "2025-26",
            [_state("A", ["a1"]), _state("B", ["b1"]), _state("C", ["c1"])],
        )
        move = Move.trade(
            (
                PlayerMovement("a1", "A", "B", _slot("a1")),
                PlayerMovement("b1", "B", "C", _slot("b1")),
                PlayerMovement("c1", "C", "A", _slot("c1")),
            )
        )
        after = apply(league, move)
        assert after.team("A").player_ids == {"c1"}
        assert after.team("B").player_ids == {"a1"}
        assert after.team("C").player_ids == {"b1"}
        assert move.multi_team is True

    def test_a_departure_leaves_the_spot_empty_rather_than_promoting_anyone(self):
        """`apply` must not invent a replacement.

        R5.5 measured that the signal share of served TEI outside a team's top ten is
        0.000, so promoting the next man up would invent production. The unfilled spot is
        the projection's problem, and this transition must leave it unfilled.
        """
        league = LeagueState.of("2025-26", [_state("A", ["a1", "a2", "a3"])])
        after = apply(league, Move.departure("a2", "A"))
        assert after.team("A").player_ids == {"a1", "a3"}
        assert len(after.team("A")) == 2

    def test_an_injury_does_not_remove_the_player_from_the_roster(self):
        """He is unavailable, not gone, and still counts against roster limits."""
        league = LeagueState.of("2025-26", [_state("A", ["a1", "a2"])])
        after = apply(league, Move.injury("a1", "A"))
        assert after.team("A").player_ids == {"a1", "a2"}

    def test_apply_does_not_reallocate_minutes_or_assign_archetypes(self):
        """The restraint that keeps the basketball model out of the data structure."""
        league = LeagueState.of("2025-26", [_state("A", ["a1", "a2"]), _state("B", [])])
        after = apply(league, Move.trade((PlayerMovement("a1", "A", "B", _slot("a1")),)))
        moved = after.team("B").get("a1")
        assert moved.minutes == 24.0  # unchanged, not re-derived
        assert moved.archetypes == ()  # not assigned
        assert after.team("A").get("a2").minutes == 24.0  # incumbent untouched

    def test_a_move_touching_a_team_absent_from_the_state_is_refused(self):
        league = LeagueState.of("2025-26", [_state("A", ["a1"])])
        with pytest.raises(ValueError, match="not in this league state"):
            apply(league, Move.trade((PlayerMovement("a1", "A", "Z", _slot("a1")),)))

    def test_a_movement_must_have_a_source_or_a_destination(self):
        with pytest.raises(ValueError):
            PlayerMovement("p1", None, None)

    def test_a_movement_onto_a_roster_must_carry_its_slot(self):
        with pytest.raises(ValueError):
            PlayerMovement("p1", "A", "B")

    def test_move_kinds_cover_the_transactions_the_roadmap_names(self):
        assert {k.value for k in MoveKind} == {
            "trade",
            "signing",
            "waiver",
            "draft",
            "departure",
            "injury",
            "rotation",
        }


class TestScenariosCanBranch:
    """§11 of the Pivot brief needs multi-step, multi-team reasoning later. These tests
    pin that the shape chosen now does not preclude it."""

    def test_a_sequence_of_moves_builds_a_lineage(self):
        league = LeagueState.of("2025-26", [_state("A", ["a1", "a2"]), _state("B", ["b1"])])
        step = replay(
            league,
            (
                Move.trade((PlayerMovement("a1", "A", "B", _slot("a1")),), label="first"),
                Move.trade((PlayerMovement("b1", "B", "A", _slot("b1")),), label="second"),
            ),
        )
        assert step.depth == 1
        assert [s.move.label for s in step.lineage()] == ["first", "second"]

    def test_two_branches_from_one_state_are_independent(self):
        league = LeagueState.of("2025-26", [_state("A", ["a1", "a2"]), _state("B", [])])
        root = ScenarioStep(move=Move.rotation("A", label="start"), state=league)
        left = root.then(Move.trade((PlayerMovement("a1", "A", "B", _slot("a1")),)))
        right = root.branch(Move.trade((PlayerMovement("a2", "A", "B", _slot("a2")),)))

        assert left.state.team("B").player_ids == {"a1"}
        assert right.state.team("B").player_ids == {"a2"}
        assert left.parent is right.parent is root
        assert root.state.team("A").player_ids == {"a1", "a2"}

    def test_replay_of_no_moves_produces_no_step(self):
        assert replay(LeagueState.of("2025-26", []), ()) is None
