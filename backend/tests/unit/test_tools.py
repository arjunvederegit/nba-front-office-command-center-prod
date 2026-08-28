"""The Copilot tool boundary.

There is no language model here and these tests exist to keep it that way. What they pin is
the shape of the seam: read-only, honest about what it cannot do, and carrying the
disclosures that stop a correct number from being repeated as a broader claim.
"""

import pytest

from app.services.tools import ToolSpec, available_tools, build_registry, unavailable_tools


@pytest.fixture()
def registry(db, seeded_league):
    return build_registry(db)


class TestTheBoundaryIsReadOnly:
    def test_every_tool_is_readonly(self, registry):
        """A conversation must not be able to change state a person never confirmed."""
        assert all(spec.readonly for spec in registry.values())

    def test_a_write_tool_cannot_be_constructed(self):
        with pytest.raises(ValueError, match="read-only"):
            ToolSpec(
                name="save_trade",
                summary="write something",
                parameters={"type": "object", "properties": {}},
                available=True,
                handler=lambda: None,
                readonly=False,
            )


class TestTheRegistryIsHonest:
    def test_an_unavailable_tool_states_why(self, registry):
        for spec in registry.values():
            if not spec.available:
                assert spec.unavailable_reason, f"{spec.name} is unavailable with no reason"

    def test_an_unavailable_tool_has_no_handler(self, registry):
        """The failure mode this prevents: a tool that is listed as unbuilt but is quietly
        callable, returning something adjacent to what was asked."""
        for spec in registry.values():
            if not spec.available:
                assert spec.handler is None

    def test_an_available_tool_must_have_a_handler(self):
        with pytest.raises(ValueError, match="must have a handler"):
            ToolSpec(
                name="x",
                summary="s",
                parameters={"type": "object", "properties": {}},
                available=True,
            )

    def test_an_unavailable_tool_cannot_be_offered_as_a_definition(self, registry):
        unbuilt = next(s for s in registry.values() if not s.available)
        with pytest.raises(ValueError, match="not available"):
            unbuilt.as_tool_definition()

    def test_the_registry_declares_the_full_vocabulary_not_just_what_is_built(self, registry):
        """The unbuilt half is the point: a Copilot discovers that Pivot cannot simulate a
        signing, rather than discovering a function that returns something adjacent."""
        # The tool vocabulary named in the Pivot brief. `get_roster_needs` is deliberately
        # absent as a separate tool: needs are part of the team profile, and two tools that
        # answer overlapping questions is how a Copilot ends up quoting two different
        # numbers for one fact.
        assert {s.name for s in registry.values()} >= {
            "get_team_profile",
            "get_player_profile",
            "get_roster",
            "search_players",
            "calculate_fit",
            "compare_players",
            "simulate_addition",
            "simulate_departure",
            "simulate_trade",
            "compare_scenarios",
        }
        assert any(not s.available for s in registry.values())
        assert any(s.available for s in registry.values())


class TestTheAvailableToolsActuallyWork:
    def test_every_available_tool_produces_a_valid_definition(self, db, seeded_league):
        for definition in available_tools(db):
            assert definition["name"]
            assert definition["description"]
            assert definition["input_schema"]["type"] == "object"

    def test_get_vocabulary_runs(self, registry):
        out = registry["get_vocabulary"].handler()
        assert out["skills"]
        assert any(not s["available"] for s in out["skills"])

    def test_get_player_profile_runs(self, registry, seeded_league):
        out = registry["get_player_profile"].handler(seeded_league["roster_a"][0].id)
        assert out["player"]["full_name"]
        assert out["skills_declared"] >= out["skills_measured"]

    def test_get_team_profile_runs(self, registry, seeded_league):
        out = registry["get_team_profile"].handler(seeded_league["team_a"].id)
        assert out["roster_size"] == 15

    def test_calculate_fit_requires_both_arguments(self, registry):
        schema = registry["calculate_fit"].parameters
        assert set(schema["required"]) == {"player_id", "team_id"}

    def test_unavailable_tools_are_reported_with_reasons(self, db, seeded_league):
        rows = unavailable_tools(db)
        assert rows
        assert all(r["reason"] for r in rows)


class TestTheCaveatsTravelWithTheResult:
    def test_fit_carries_the_magnitude_caveat(self, registry):
        """`fit` measures the direction of a change, not its size. Quoted without that, a
        bench player who answers a need reads as a better acquisition than a star."""
        caveats = " ".join(registry["calculate_fit"].result_caveats).lower()
        assert "direction" in caveats and "size" in caveats

    def test_player_profile_forbids_calling_an_unmeasured_player_average(self, registry):
        caveats = " ".join(registry["get_player_profile"].result_caveats).lower()
        assert "average" in caveats

    def test_team_profile_forbids_inventing_an_answer_to_an_unaddressable_need(self, registry):
        caveats = " ".join(registry["get_team_profile"].result_caveats).lower()
        assert "unaddressable_reason" in caveats
