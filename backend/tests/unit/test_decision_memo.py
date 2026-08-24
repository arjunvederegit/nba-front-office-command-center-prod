"""The decision memo is the highest-stakes artifact in the product.

Three properties matter more than its prose: it never prints a score for a deal that
cannot be executed, no section renders empty, and everything it could not establish ends
up in one place a reader will actually look.
"""

import pytest

from app.services.reports import MATERIAL_MINUTES, build_report_markdown, memo_payload


def _base(**overrides):
    payload = {
        "trade_name": "Fixture deal",
        "focal_team_name": "Alpha Test Club",
        "strategy": "contend",
        "legality": {"overall_status": "conditionally_valid", "rule_results": []},
        "evaluations": {"team-a": {"team_id": "team-a", "composite_utility": 61.0}},
        "focal_team_id": "team-a",
    }
    payload.update(overrides)
    return payload


def sections(markdown: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    current: str | None = None
    for line in markdown.splitlines():
        if line.startswith("## "):
            current = line[3:]
            found[current] = []
        elif current is not None and line.strip():
            found[current].append(line)
    return found


def test_no_section_renders_empty():
    """An empty section reads as 'nothing to say here', which for a cost section that
    could not be computed is the opposite of the truth."""
    markdown = build_report_markdown(**_base())
    for name, body in sections(markdown).items():
        assert body, f"section rendered empty: {name}"


def test_every_section_a_memo_needs_is_present():
    markdown = build_report_markdown(**_base())
    names = list(sections(markdown))
    assert names[0] == "Recommendation"
    for expected in (
        "1. What changes on the floor",
        "2. Does it fit this roster",
        "3. What it costs",
        "4. Rules",
        "5. Precedent",
        "6. Risks",
        "What is not known",
        "Assumptions and provenance",
    ):
        assert expected in names


def test_an_illegal_deal_prints_no_score_and_names_the_rules():
    markdown = build_report_markdown(
        **_base(
            evaluations={
                "team-a": {
                    "decision_status": "suppressed_illegal",
                    "suppression": {
                        "failing_rules": [
                            {"rule_code": "ROSTER_SIZE", "message": "19 players is too many"}
                        ]
                    },
                }
            },
            legality={"overall_status": "verified_illegal", "rule_results": []},
        )
    )
    assert "Do not proceed — the trade fails implemented CBA rules" in markdown
    assert "Composite utility" not in markdown
    assert "ROSTER_SIZE" in markdown


def test_unavailable_facts_are_collected_into_one_section():
    markdown = build_report_markdown(
        **_base(
            evaluations={
                "team-a": {
                    "composite_utility": 55.0,
                    "excluded_components": ["contract", "assets"],
                    "unmodeled_players": ["Nobody Measured"],
                    "detail": {
                        "fit": {"unavailable": "team needs not computed"},
                        "risk": {"unavailable": "no measured availability"},
                        "roster_shape": {"unavailable": "rotation not projected"},
                    },
                }
            }
        )
    )
    unknown = "\n".join(sections(markdown)["What is not known"])
    assert "contract, assets" in unknown
    assert "Nobody Measured" in unknown
    assert "team needs not computed" in unknown
    assert "no measured availability" in unknown
    assert "rotation not projected" in unknown


def test_a_memo_with_nothing_missing_says_so_rather_than_leaving_a_gap():
    markdown = build_report_markdown(
        **_base(
            evaluations={
                "team-a": {
                    "composite_utility": 55.0,
                    "excluded_components": [],
                    "unmodeled_players": [],
                    "legality": {
                        "payroll_after": 180_000_000,
                        "apron_status_after": "below first apron",
                        "incoming_salary": 20_000_000,
                        "outgoing_salary": 19_000_000,
                    },
                    "detail": {
                        "fit": {"needs_addressed": {"three_point_volume": 0.2}},
                        "assets": {"picks_priced": [], "picks_not_priced": []},
                        "risk": {"availability_delta": 0.02},
                    },
                }
            }
        )
    )
    assert "Nothing this memo relies on was unavailable." in markdown


def test_only_roles_that_actually_moved_are_tabulated():
    """Fourteen rows is a table nobody reads."""
    roles = [
        {
            "role": "stretch big",
            "minutes_before": 10.0,
            "minutes_after": 30.0,
            "delta": 20.0,
            "league_median": 8.0,
            "league_threshold": 20.0,
            "congested": True,
            "lost": False,
        },
        {
            "role": "lead guard",
            "minutes_before": 40.0,
            "minutes_after": 39.5,
            "delta": -0.5,
            "league_median": 35.0,
            "league_threshold": 60.0,
            "congested": False,
            "lost": False,
        },
    ]
    markdown = build_report_markdown(
        **_base(
            evaluations={
                "team-a": {
                    "composite_utility": 55.0,
                    "detail": {
                        "performance": {"delta_wins": 1.2, "delta_net_rating": 0.5},
                        "roster_shape": {"roles": roles, "lineup_fit": {"available": False,
                            "reason": "measured", "recheck": "make lineup-availability"}},
                    },
                }
            }
        )
    )
    assert "stretch big" in markdown
    assert "| lead guard |" not in markdown
    assert MATERIAL_MINUTES == 2.0
    assert "Lineup-aware fit is unavailable" in markdown


def test_comparables_carry_the_resemblance_is_not_consequence_warning():
    markdown = build_report_markdown(
        **_base(
            comparables={
                "available": True,
                "coverage": {"sides_rankable": 337, "trades_ingested": 565},
                "not_scored": [{"field": "salary", "reason": "no historical contracts"}],
                "comparables": [
                    {
                        "team_abbreviation": "BOS",
                        "transaction_date": "2025-07-07",
                        "similarity": 0.81,
                        "source_text": "The BOS traded X to the POR for Y.",
                        "why": ["draft capital: 100% similar"],
                    }
                ],
            }
        )
    )
    precedent = "\n".join(sections(markdown)["5. Precedent"])
    assert "BOS" in precedent
    assert "Resemblance is not consequence" in precedent
    unknown = "\n".join(sections(markdown)["What is not known"])
    assert "does not score salary" in unknown


def test_unavailable_comparables_are_reported_not_omitted():
    markdown = build_report_markdown(
        **_base(
            comparables={
                "available": False,
                "unavailable_reason": "no completed trade has modelled production",
            }
        )
    )
    assert "no completed trade has modelled production" in markdown
    unknown = "\n".join(sections(markdown)["What is not known"])
    assert "Historical precedent" in unknown


def test_the_memo_payload_lists_its_own_sections():
    markdown = build_report_markdown(**_base())
    payload = memo_payload(markdown)
    assert payload["markdown"] == markdown
    assert "Recommendation" in payload["sections"]
    assert payload["generated_at"]


@pytest.mark.parametrize(
    ("utility", "expected"),
    [
        (70.0, "Proceed with further diligence"),
        (50.0, "Neutral — depends on strategic priorities"),
        (20.0, "Do not proceed as constructed"),
        (None, "No recommendation — this deal could not be scored"),
    ],
)
def test_the_verdict_is_monotone_in_the_composite(utility, expected):
    markdown = build_report_markdown(
        **_base(evaluations={"team-a": {"composite_utility": utility}})
    )
    assert expected in markdown
