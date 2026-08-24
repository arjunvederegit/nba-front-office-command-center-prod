"""The validation battery itself has to work, and its nulls have to be nulls.

The numbers in `ROSTERLAB_R6_IMPLEMENTATION_REPORT.md` come from running this over the
real corpus. What is asserted here is the machinery: that a null really destroys the
signal, that a threshold failure is reported rather than swallowed, and that the battery
runs end to end on a corpus small enough for a test.
"""

from datetime import date

import pytest

from app.analytics.comparables import PickLeg, PlayerLeg, TradeSide, robust_scales
from app.analytics.comparables_validation import (
    THRESHOLDS,
    _is_asymmetric,
    _MirroredSide,
    archetype_of,
    archetype_precision,
    era_structure,
    random_ranker,
    run_battery,
    sd_scales,
    season_concentration,
    shuffled_corpus,
)


def side(key: str, **overrides) -> TradeSide:
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


def leg(name: str, tei: float, minutes: float = 30.0, age: float = 27.0) -> PlayerLeg:
    return PlayerLeg(name=name, player_id=name, tei=tei, minutes=minutes, age=age)


@pytest.fixture()
def corpus() -> list[TradeSide]:
    """A small corpus containing both directional archetypes and some filler."""
    sides: list[TradeSide] = []
    for i in range(6):
        sides.append(
            side(
                f"sell{i}",
                outgoing=(leg(f"star{i}", 2.5 + i * 0.2),),
                picks_in=tuple(PickLeg(2029 + j, 1) for j in range(2)),
                win_pct=0.3 + i * 0.02,
            )
        )
        sides.append(
            side(
                f"buy{i}",
                incoming=(leg(f"star{i}", 2.5 + i * 0.2),),
                picks_out=tuple(PickLeg(2029 + j, 1) for j in range(2)),
                win_pct=0.6 + i * 0.02,
            )
        )
        sides.append(
            side(
                f"swap{i}",
                incoming=(leg(f"a{i}", 0.3 + i * 0.05),),
                outgoing=(leg(f"b{i}", 0.28 + i * 0.05),),
                win_pct=0.5,
            )
        )
    return sides


def test_the_battery_runs_and_reports_every_check(corpus):
    report = run_battery(corpus, k=3)
    names = [c["name"] for c in report["checks"]]
    assert "perturbation_stability" in names
    assert "archetype_recovery" in names
    assert "direction_confusion" in names
    assert "era_structure" in names
    assert report["corpus_sides"] == len(corpus)
    assert report["weights"]
    # Every gated check reports a threshold and a verdict; ungated ones report neither.
    for check in report["checks"]:
        assert (check["threshold"] is None) == (check["passed"] is None)


def test_the_random_null_lands_on_the_base_rate(corpus):
    scales = robust_scales(corpus)
    real = archetype_precision(corpus, scales, k=3)
    null = archetype_precision(corpus, scales, k=3, ranker=random_ranker(3))
    assert real["precision_at_k"] > null["precision_at_k"]
    assert null["precision_at_k"] == pytest.approx(null["base_rate"], abs=0.25)


def test_the_shuffled_null_keeps_the_marginals_and_destroys_the_correspondence(corpus):
    swapped = shuffled_corpus(corpus)
    assert {s.key for s in swapped} == {s.key for s in corpus}
    def vector(entry) -> str:
        return repr(sorted(entry.features().items()))

    originals = sorted(vector(s) for s in corpus)
    shuffled = sorted(vector(s) for s in swapped)
    assert originals == shuffled  # same multiset of vectors...
    assert any(
        s.features() != next(o for o in corpus if o.key == s.key).features() for s in swapped
    )  # ...attached to different sides


def test_a_directional_side_is_asymmetric_and_a_swap_is_not(corpus):
    assert _is_asymmetric(next(s for s in corpus if s.key == "sell0"))
    assert not _is_asymmetric(next(s for s in corpus if s.key == "swap0"))


def test_mirroring_reverses_every_directional_feature(corpus):
    original = next(s for s in corpus if s.key == "sell0")
    mirrored = _MirroredSide(original)
    before, after = original.features(), mirrored.features()
    assert after["firsts_net"] == -before["firsts_net"]
    assert after["value_in"] == before["value_out"]
    assert after["picks_in"] == before["picks_out"]
    assert after["players_out"] == before["players_in"]
    # ...and leaves the direction-invariant ones alone, which is why the mirror is
    # measured by rank rather than by similarity level.
    assert after["n_teams"] == before["n_teams"]
    assert after["is_in_season"] == before["is_in_season"]


def test_direction_confusion_is_measured_between_opposites_only(corpus):
    report = run_battery(corpus, k=3)
    check = next(c for c in report["checks"] if c["name"] == "direction_confusion")
    assert check["threshold"] == THRESHOLDS["direction_confusion_max"]
    assert check["detail"]["directional_neighbours"] > 0


def test_sd_scales_cover_the_features_that_vary(corpus):
    scales = sd_scales(corpus)
    assert scales["value_out"] > 0
    assert "is_in_season" not in scales  # constant in this corpus, so it has no sd


def test_season_concentration_reports_its_own_base_rate(corpus):
    result = season_concentration(corpus, robust_scales(corpus), k=3)
    assert result["base_rate"] == pytest.approx(1.0)  # one season only
    assert result["same_feature_season_share"] == pytest.approx(1.0)


def test_era_structure_needs_no_player_model(corpus):
    older = [
        side(f"old{i}", season="2021-22", picks_in=(PickLeg(2024, 2),)) for i in range(3)
    ]
    summary = era_structure([*corpus, *older])
    assert summary["2017_cba"]["sides"] == 3
    assert summary["2023_cba"]["sides"] == len(corpus)
    assert summary["2023_cba"]["mean_picks_per_side"] > 0


def test_a_failing_threshold_is_listed_rather_than_swallowed(corpus, monkeypatch):
    monkeypatch.setitem(THRESHOLDS, "perturbation_overlap_min", 1.01)
    report = run_battery(corpus, k=3)
    assert "perturbation_stability" in report["failed"]


def test_archetype_rules_assign_at_most_one_class(corpus):
    for entry in corpus:
        label = archetype_of(entry)
        assert label is None or isinstance(label, str)
