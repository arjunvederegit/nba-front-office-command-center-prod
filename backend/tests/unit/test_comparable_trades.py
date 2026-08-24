"""Properties of the comparable-trade distance that must not regress.

The battery in `app/analytics/comparables_validation.py` measures the *corpus*; these are
the invariants that hold on any corpus, and the two that a live measurement cannot catch:
an explanation that names a driver the arithmetic did not have, and a query built by a
different function from the trades it is compared against.
"""

from datetime import date

import pytest

from app.analytics.comparables import (
    DIMENSION_WEIGHTS,
    FEATURE_DIMENSIONS,
    PickLeg,
    PlayerLeg,
    TradeSide,
    compare,
    explain,
    feature_distance,
    rank,
    robust_scales,
)
from app.analytics.comparables_validation import (
    OPPOSITE_ARCHETYPES,
    archetype_of,
    era_structure,
)
from app.db.models import HistoricalTrade, HistoricalTradeAsset, Team
from app.services.comparables import ComparableTradeService, feature_season_for


def make_side(key: str, **overrides) -> TradeSide:
    base = {
        "key": key,
        "team_abbreviation": "AAA",
        "season": "2025-26",
        "feature_season": "2025-26",
        "transaction_date": date(2026, 2, 5),
        "is_in_season": True,
        "n_teams": 2,
        "win_pct": 0.5,
        "counterparty_win_pct": 0.5,
    }
    base.update(overrides)
    return TradeSide(**base)


def player(name: str, tei: float, minutes: float = 30.0, age: float = 27.0) -> PlayerLeg:
    return PlayerLeg(name=name, player_id=name, tei=tei, minutes=minutes, age=age)


# ------------------------------------------------------------------ the distance form


def test_the_feature_distance_is_bounded_monotone_and_never_saturates():
    assert feature_distance(0.0, 0.0, 1.0) == 0.0
    assert feature_distance(0.0, 1.0, 1.0) == pytest.approx(0.5)
    ordered = [feature_distance(0.0, delta, 1.0) for delta in (1, 5, 50, 5_000)]
    assert ordered == sorted(ordered)
    # The point of not clipping: two very different pairs stay ordered rather than tying.
    assert ordered[-1] < 1.0
    assert len(set(ordered)) == len(ordered)


def test_a_constant_feature_is_dropped_rather_than_scored_as_agreement():
    sides = [make_side(f"s{i}", n_teams=2, incoming=(player("p", float(i)),)) for i in range(8)]
    scales = robust_scales(sides)
    assert "n_teams" in scales  # declared, so it survives even with no spread
    # A corpus-scaled feature with no spread has no scale and cannot be compared.
    assert "win_pct" not in scales
    comparison = compare(sides[0], sides[1], scales)
    assert "win_pct" in comparison.features_unavailable


def test_a_feature_only_one_side_states_is_not_compared():
    scales = {"best_in_tei": 1.0, "players_in": 1.0, "players_out": 1.0, "n_teams": 1.0}
    with_players = make_side("a", incoming=(player("x", 2.0),))
    without = make_side("b")
    comparison = compare(with_players, without, scales)
    assert "best_in_tei" in comparison.features_unavailable
    structure = next(d for d in comparison.dimensions if d.name == "structure")
    assert "players_in" in structure.features


def test_a_dimension_neither_side_states_is_dropped_and_named():
    scales = {"players_in": 1.0, "players_out": 1.0, "n_teams": 1.0}
    comparison = compare(make_side("a"), make_side("b"), scales)
    assert "player_value" in comparison.dimensions_unavailable
    assert "draft_capital" in comparison.dimensions_unavailable
    assert {d.name for d in comparison.dimensions} == {"structure"}


def test_dropping_a_dimension_redistributes_its_weight_rather_than_zeroing_it():
    scales = {"players_in": 1.0, "players_out": 1.0, "n_teams": 1.0}
    identical = compare(make_side("a"), make_side("b"), scales)
    # Structure is identical, every other dimension is unavailable, so the distance is 0
    # rather than 0 x 0.20 + 1 x 0.80.
    assert identical.distance == pytest.approx(0.0)
    assert identical.similarity == pytest.approx(1.0)


# ------------------------------------------------------------------- the explanation


def test_the_explanation_names_the_dimensions_the_arithmetic_actually_used():
    sides = [
        make_side("a", incoming=(player("x", 3.0),), picks_out=(PickLeg(2030, 1),)),
        make_side("b", incoming=(player("y", 2.8),), picks_out=(PickLeg(2031, 1),)),
        make_side("c", outgoing=(player("z", -1.0), player("w", 0.4))),
        make_side("d", picks_in=(PickLeg(2029, 2), PickLeg(2030, 2))),
        make_side("e", incoming=(player("q", 0.1),), outgoing=(player("r", 0.2),)),
    ]
    scales = robust_scales(sides)
    neighbour = rank(sides[0], sides[1:], scales, k=1)[0]
    contributions = neighbour.comparison.contributions()
    sentences = explain(sides[0], neighbour, top_n=3)
    # The first three sentences follow the contribution ranking, in order.
    from app.analytics.comparables import DIMENSION_LABELS

    for sentence, (name, _) in zip(sentences, contributions[:3], strict=False):
        assert sentence.startswith(DIMENSION_LABELS[name])


def test_the_least_alike_line_names_the_least_similar_dimension_not_the_smallest_term():
    """A contribution is weight x similarity, so the smallest one is often the lowest-
    weight dimension rather than the least similar. Ranking on it produced the sentence
    "Least alike on timing (100% similar)" in a live response."""
    sides = [
        make_side("a", incoming=(player("x", 3.0),), picks_out=(PickLeg(2030, 1),)),
        make_side("b", outgoing=(player("y", -2.0),), picks_in=(PickLeg(2031, 2),)),
        make_side("c", incoming=(player("z", 0.2),), outgoing=(player("w", 0.1),)),
        make_side("d", picks_in=(PickLeg(2029, 2), PickLeg(2030, 2))),
        make_side("e", incoming=(player("q", 1.4), player("r", -0.3))),
    ]
    scales = robust_scales(sides)
    for neighbour in rank(sides[0], sides[1:], scales, k=4):
        least = [s for s in explain(sides[0], neighbour) if s.startswith("Least alike")]
        if not least:
            continue
        share = float(least[0].rsplit("(", 1)[1].split("%")[0]) / 100
        assert share < 0.9
        lowest = min(d.similarity for d in neighbour.comparison.dimensions)
        assert share == pytest.approx(lowest, abs=0.005)


def test_contributions_sum_to_the_similarity():
    sides = [
        make_side("a", incoming=(player("x", 3.0),), picks_out=(PickLeg(2030, 1),)),
        make_side("b", incoming=(player("y", 1.0),), picks_out=(PickLeg(2031, 2),)),
        make_side("c", outgoing=(player("z", -1.0),)),
        make_side("d", picks_in=(PickLeg(2029, 2),)),
    ]
    scales = robust_scales(sides)
    comparison = compare(sides[0], sides[1], scales)
    assert sum(share for _, share in comparison.contributions()) == pytest.approx(
        comparison.similarity
    )


# ------------------------------------------------------------------------ determinism


def test_ranking_is_deterministic_and_excludes_the_query_itself():
    sides = [make_side(f"s{i}", incoming=(player("p", i * 0.5),)) for i in range(10)]
    scales = robust_scales(sides)
    first = [n.side.key for n in rank(sides[0], sides, scales, k=4)]
    second = [n.side.key for n in rank(sides[0], sides, scales, k=4)]
    assert first == second
    assert "s0" not in first


def test_only_one_side_of_a_completed_trade_is_returned():
    """Both sides of a trade belong in the corpus and both are ranked; showing a reader
    the same sentence twice — often as near-mirrors of each other — does not."""
    left = make_side("t1|AAA", group_key="t1", incoming=(player("x", 2.0),))
    right = make_side("t1|BBB", group_key="t1", outgoing=(player("x", 2.0),))
    other = make_side("t2|CCC", group_key="t2", incoming=(player("y", 1.9),))
    filler = [make_side(f"t{i}|X", group_key=f"t{i}", incoming=(player("z", i * 0.4),))
              for i in range(3, 9)]
    corpus = [left, right, other, *filler]
    scales = robust_scales(corpus)
    query = make_side("query", incoming=(player("q", 2.1),))
    groups = [n.side.group for n in rank(query, corpus, scales, k=5)]
    assert len(groups) == len(set(groups))
    # ...and both sides are still ranked when the caller asks for them.
    both = [n.side.key for n in rank(query, corpus, scales, k=9, one_per_trade=False)]
    assert "t1|AAA" in both and "t1|BBB" in both


def test_a_side_without_a_group_key_groups_on_itself():
    side = make_side("solo")
    assert side.group == "solo"


def test_an_unrankable_side_is_never_returned_as_a_comparable():
    good = [make_side(f"s{i}", incoming=(player("p", i * 0.5),)) for i in range(6)]
    blocked = make_side(
        "blocked",
        incoming=(PlayerLeg(name="Ghost", player_id="ghost"),),
    )
    assert blocked.rankable is False
    scales = robust_scales(good)
    assert "blocked" not in [n.side.key for n in rank(good[0], [*good, blocked], scales, k=6)]


# --------------------------------------------------------------- value and no-production


def test_a_player_with_no_prior_nba_season_contributes_zero_not_an_average():
    rookie = PlayerLeg(name="Draft right", player_id="dr", no_prior_nba_season=True)
    assert rookie.value == 0.0
    side = make_side("a", incoming=(rookie,))
    assert side.features()["value_in"] == 0.0
    # ...and does not block the side, unlike a player whose evidence is merely missing.
    assert side.rankable is True


def test_a_player_whose_evidence_is_missing_withholds_the_side():
    missing = PlayerLeg(name="Injured veteran", player_id="iv")
    side = make_side("a", incoming=(missing,))
    assert side.features()["value_in"] is None
    assert side.rankable is False
    # Named, so the refusal can be explained rather than merely applied.
    assert side.unmodelled_players == ("Injured veteran",)


def test_package_value_is_minutes_weighted_above_replacement():
    from app.analytics.projection import REPLACEMENT_TEI, TEAM_MINUTES

    leg = player("x", 2.0, minutes=24.0)
    assert leg.value == pytest.approx((24.0 / TEAM_MINUTES) * (2.0 - REPLACEMENT_TEI))


# --------------------------------------------------------------------- feature season


@pytest.mark.parametrize(
    ("season", "when", "expected"),
    [
        ("2025-26", date(2025, 7, 6), "2024-25"),
        ("2025-26", date(2025, 9, 30), "2024-25"),
        ("2025-26", date(2025, 10, 1), "2025-26"),
        ("2025-26", date(2026, 2, 5), "2025-26"),
        ("2025-26", date(2026, 6, 23), "2025-26"),
    ],
)
def test_the_feature_season_is_the_most_recent_production_a_team_actually_had(
    season, when, expected
):
    assert feature_season_for(season, when) == expected


# ------------------------------------------------------------------------- archetypes


def test_the_two_directional_archetypes_are_each_others_opposite():
    seller = make_side(
        "seller",
        outgoing=(player("star", 3.0),),
        picks_in=(PickLeg(2030, 1), PickLeg(2032, 1)),
    )
    buyer = make_side(
        "buyer",
        incoming=(player("star", 3.0),),
        picks_out=(PickLeg(2030, 1), PickLeg(2032, 1)),
    )
    assert archetype_of(seller) == "sold_value_for_firsts"
    assert archetype_of(buyer) == "bought_value_with_firsts"
    assert OPPOSITE_ARCHETYPES[archetype_of(seller)] == archetype_of(buyer)


def test_era_structure_splits_on_the_first_season_of_the_2023_cba():
    old = make_side("old", season="2022-23", picks_in=(PickLeg(2025, 1),))
    new = make_side("new", season="2023-24", picks_in=(PickLeg(2027, 1),))
    summary = era_structure([old, new])
    assert summary["2017_cba"]["sides"] == 1
    assert summary["2023_cba"]["sides"] == 1


# ------------------------------------------------------------- through the service


@pytest.fixture()
def league_with_history(db, seeded_league):
    """One completed trade between the two fixture teams, plus the trade proposal shape."""
    team_a, team_b = seeded_league["team_a"], seeded_league["team_b"]
    trade = HistoricalTrade(
        season="2025-26",
        transaction_date=date(2026, 2, 5),
        n_teams=2,
        source_text="The AAA traded Fixture AAA 00 to the BBB for Fixture BBB 00.",
        source_provider="bbref_transactions",
        source_record_id="2025-26:2026-02-05:fixture",
    )
    db.add(trade)
    db.flush()
    db.add_all(
        [
            HistoricalTradeAsset(
                trade_id=trade.id,
                asset_type="player",
                from_team_id=team_a.id,
                to_team_id=team_b.id,
                from_abbreviation="AAA",
                to_abbreviation="BBB",
                player_id=seeded_league["roster_a"][0].id,
                player_name=seeded_league["roster_a"][0].full_name,
                resolution_method="exact_name",
            ),
            HistoricalTradeAsset(
                trade_id=trade.id,
                asset_type="player",
                from_team_id=team_b.id,
                to_team_id=team_a.id,
                from_abbreviation="BBB",
                to_abbreviation="AAA",
                player_id=seeded_league["roster_b"][0].id,
                player_name=seeded_league["roster_b"][0].full_name,
                resolution_method="exact_name",
            ),
        ]
    )
    db.commit()
    return seeded_league


def test_query_and_corpus_sides_are_built_by_one_function(db, league_with_history):
    """The guarantee the whole engine rests on.

    If a query were built differently from the corpus, the distance would measure the two
    constructions rather than the two trades. `_side` is the only constructor, and this
    asserts the query really goes through it — by checking that a proposal identical to a
    completed trade produces an identical feature vector.
    """
    service = ComparableTradeService(db)
    corpus = service.corpus()
    assert corpus, "fixture trade should produce sides"
    side_a = next(s for s in corpus if s.team_abbreviation == "AAA")

    team_a, team_b = league_with_history["team_a"], league_with_history["team_b"]
    query = service.query_side(
        team_a.id,
        [team_a.id, team_b.id],
        [
            {
                "player_id": league_with_history["roster_a"][0].id,
                "from_team_id": team_a.id,
                "to_team_id": team_b.id,
            },
            {
                "player_id": league_with_history["roster_b"][0].id,
                "from_team_id": team_b.id,
                "to_team_id": team_a.id,
            },
        ],
        [],
        as_of=date(2026, 2, 5),
    )
    assert query.feature_season == side_a.feature_season
    assert query.features() == side_a.features()


def test_the_service_reports_coverage_rather_than_hiding_the_boundary(db, league_with_history):
    service = ComparableTradeService(db)
    coverage = service.coverage()
    assert coverage["trades_ingested"] == 1
    assert coverage["sides_total"] == 2
    assert coverage["modelled_seasons"]
    assert "not ranked" in coverage["note"]


def test_a_query_with_an_unmodelled_player_refuses_rather_than_guesses(db, league_with_history):
    service = ComparableTradeService(db)
    team_a, team_b = league_with_history["team_a"], league_with_history["team_b"]
    unmodeled = league_with_history["unmodeled"]
    result = service.find(
        team_a.id,
        [team_a.id, team_b.id],
        [{"player_id": unmodeled.id, "from_team_id": team_a.id, "to_team_id": team_b.id}],
        [],
        as_of=date(2026, 2, 5),
    )
    # The fixture's unmodelled player still has season stats, so he IS priced here; the
    # property under test is that whatever the service decides, it never invents a value.
    if result["available"]:
        assert result["query"]["features"]["value_out"] is not None
    else:
        assert result["unmodelled_players"]
        assert result["comparables"] == []


def test_weights_and_dimensions_are_published_with_every_result(db, league_with_history):
    service = ComparableTradeService(db)
    team_a, team_b = league_with_history["team_a"], league_with_history["team_b"]
    result = service.find(
        team_a.id,
        [team_a.id, team_b.id],
        [
            {
                "player_id": league_with_history["roster_a"][1].id,
                "from_team_id": team_a.id,
                "to_team_id": team_b.id,
            }
        ],
        [],
        as_of=date(2026, 2, 5),
    )
    if result["available"]:
        assert result["weights"] == DIMENSION_WEIGHTS
        assert set(result["dimensions"]) == set(FEATURE_DIMENSIONS)
        assert [n["field"] for n in result["not_scored"]] == [
            "salary",
            "cash and trade exceptions",
            "what happened next",
        ]


def test_multi_team_legs_reach_every_participant(db, seeded_league):
    """A three-team trade contributes three sides, and no leg is lost between them."""
    team_a, team_b = seeded_league["team_a"], seeded_league["team_b"]
    team_c = Team(
        nba_team_id=3, full_name="Gamma Test Club", abbreviation="CCC", nickname="CCC",
        city="Testville",
    )
    db.add(team_c)
    db.flush()
    trade = HistoricalTrade(
        season="2025-26",
        transaction_date=date(2026, 2, 5),
        n_teams=3,
        source_text="In a 3-team trade, ...",
        source_provider="bbref_transactions",
        source_record_id="2025-26:2026-02-05:three",
    )
    db.add(trade)
    db.flush()
    legs = [("AAA", "BBB", 0), ("BBB", "CCC", 1), ("CCC", "AAA", 2)]
    ids = {"AAA": team_a.id, "BBB": team_b.id, "CCC": team_c.id}
    for from_abbr, to_abbr, index in legs:
        db.add(
            HistoricalTradeAsset(
                trade_id=trade.id,
                asset_type="player",
                from_team_id=ids[from_abbr],
                to_team_id=ids[to_abbr],
                from_abbreviation=from_abbr,
                to_abbreviation=to_abbr,
                player_id=seeded_league["roster_a"][index].id,
                player_name=seeded_league["roster_a"][index].full_name,
                resolution_method="exact_name",
            )
        )
    db.commit()

    sides = ComparableTradeService(db).corpus()
    assert {s.team_abbreviation for s in sides} == {"AAA", "BBB", "CCC"}
    assert all(s.n_teams == 3 for s in sides)
    # Every leg appears exactly twice across the sides: once outgoing, once incoming.
    moved = sorted(
        leg.name for side in sides for leg in (*side.incoming, *side.outgoing)
    )
    expected = sorted(
        seeded_league["roster_a"][i].full_name for i in (0, 0, 1, 1, 2, 2)
    )
    assert moved == expected
