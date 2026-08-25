"""`data/cba/nba_cap_parameters.yml` is a committed reference dataset, so the properties
that made it safe to commit have to stay true: every season carries an explicit status,
confirmed and projected values are never conflated, every row names its source, and the
one confirmed season agrees with the YAML `make seed-config` actually loads.

The last check is the one with teeth. Two files carrying 2026-27 cap thresholds is a
divergence waiting to happen, and a silent disagreement would put a projected number
behind a rule that reports itself as confirmed.
"""

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DATASET = REPO_ROOT / "data" / "cba" / "nba_cap_parameters.yml"
SEEDED = REPO_ROOT / "backend" / "app" / "config" / "cap_rules"

ALLOWED_STATUSES = {"confirmed", "nba_estimate", "projected"}


@pytest.fixture(scope="module")
def dataset() -> dict:
    if not DATASET.exists():  # pragma: no cover - the file is committed
        pytest.skip(f"{DATASET} is not present")
    return yaml.safe_load(DATASET.read_text())


def test_every_season_declares_an_explicit_status(dataset: dict) -> None:
    seasons = dataset["seasons"]
    assert seasons, "the dataset carries no seasons"
    for row in seasons:
        assert row["status"] in ALLOWED_STATUSES, f"{row['season']} has status {row['status']!r}"
        assert row["confirmation_or_projection"], f"{row['season']} does not justify its status"
        assert row["source_name"], f"{row['season']} names no source"


def test_confirmed_and_projected_are_not_conflated(dataset: dict) -> None:
    """Exactly one season is confirmed, and it is the league year the product evaluates
    under. A second `confirmed` row would mean someone promoted a projection."""
    confirmed = [row["season"] for row in dataset["seasons"] if row["status"] == "confirmed"]
    assert confirmed == ["2026-27"], f"unexpected confirmed seasons: {confirmed}"

    projected = [row for row in dataset["seasons"] if row["status"] != "confirmed"]
    assert projected, "a dataset with no projections would not need a status field"
    for row in projected:
        assert "projection" in row["notes"].lower() or "estimate" in row["notes"].lower()


def test_the_dataset_attributes_its_sources(dataset: dict) -> None:
    sources = dataset["sources"]
    named = {source["name"] for source in sources}
    assert "NBA Communications" in named
    for source in sources:
        assert source["url"].startswith("https://")
        assert source["scope"]


def test_confirmed_season_agrees_with_the_seeded_cap_rules(dataset: dict) -> None:
    """The seeded YAML is the source of truth for the engine; this dataset must not
    disagree with it for the season both describe."""
    confirmed = next(row for row in dataset["seasons"] if row["status"] == "confirmed")
    seeded = yaml.safe_load((SEEDED / f"{confirmed['season']}.yaml").read_text())
    params = seeded["parameters"]

    assert confirmed["salary_cap"] == params["salary_cap"]
    assert confirmed["luxury_tax"] == params["luxury_tax"]
    assert confirmed["first_apron"] == params["first_apron"]
    assert confirmed["second_apron"] == params["second_apron"]
    assert confirmed["salary_floor"] == params["minimum_team_salary"]


def test_thresholds_are_ordered_within_every_season(dataset: dict) -> None:
    for row in dataset["seasons"]:
        assert row["salary_floor"] < row["salary_cap"] < row["luxury_tax"], row["season"]
        assert row["luxury_tax"] < row["first_apron"] < row["second_apron"], row["season"]
        assert row["taxpayer_mle"] < row["room_mle"] < row["non_taxpayer_mle"], row["season"]
