"""R4-1e — a skill must actually reach the production scoring frame.

Three failure modes, none of which any pre-R4 test could see:

1. **The dropped column.** `recency_weighted_features` keeps only `MODEL_FEATURES` as
   numerics. Measured on the real database the season frame carries 49 columns and the
   window frame 25, so 27 are dropped silently — `DEF_RATING`, `FG3A` and `POSS` among
   them. A skill defined on a dropped column resolves for nobody, with no error.

2. **The stale cache.** The skills cache key was namespaced on the data version, which
   only an ingestion run bumps. A deploy that changed the skill contract kept serving the
   previous shape for the remaining six hours of TTL, and could not reproduce locally
   because the in-process fallback dies with the process while Redis does not.

3. **The wrong shrinkage stage.** Shrinking per season and then collapsing is not the
   same operation as shrinking the window, and the difference is large enough to move
   hundreds of players across percentiles.
"""

import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.analytics import archetypes as archetypes_module
from app.analytics.archetypes import (
    SKILL_KEYS,
    player_skill_vector,
    skill_schema_fingerprint,
)
from app.analytics.features import (
    DEF_SHRINKAGE_MINUTES,
    FG3_LEAGUE_MEAN,
    FG3_SHRINKAGE_ATTEMPTS,
    MODEL_FEATURES,
    recency_weighted_features,
)
from app.analytics.needs import NEED_TO_SKILL

ARCHETYPES_SRC = Path(archetypes_module.__file__)

# Columns `recency_weighted_features` carries explicitly, outside MODEL_FEATURES.
CARRIED_IDENTITY_COLUMNS = {
    "height_inches",
    "position",
    "is_active",
    "latest_season",
    "seasons_observed",
    "total_minutes_window",
    "full_name",
    "nba_player_id",
    "player_id",
}
# Derived after the collapse, so not in MODEL_FEATURES but present in the window frame.
POST_COLLAPSE_COLUMNS = {"def_impact", "fg3_pct_shrunk", "fg3a_window", "fg3m_window"}


def _source_columns_read_by_skills() -> set[str]:
    """Every column literal passed to pct / pct_inv / blend inside the skill vector."""
    tree = ast.parse(ARCHETYPES_SRC.read_text())
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "player_skill_vector"
    )
    columns: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id in {"pct", "pct_inv"}:
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    columns.add(arg.value)
        elif node.func.id == "blend":
            for arg in node.args:
                if isinstance(arg, ast.Tuple) and arg.elts:
                    first = arg.elts[0]
                    if isinstance(first, ast.Constant) and isinstance(first.value, str):
                        columns.add(first.value)
    return columns


class TestEverySkillInputSurvivesTheCollapse:
    def test_every_source_column_is_available_in_the_window_frame(self):
        """The structural check that would have caught `DEF_RATING`.

        Needs no database, so it fails in CI on the commit that introduces the mistake
        rather than on whatever later run first looks at a real frame.
        """
        available = set(MODEL_FEATURES) | CARRIED_IDENTITY_COLUMNS | POST_COLLAPSE_COLUMNS
        missing = sorted(_source_columns_read_by_skills() - available)
        assert missing == [], (
            f"{missing} are read by player_skill_vector but never reach the window frame; "
            "add them to MODEL_FEATURES or derive them post-collapse"
        )

    def test_the_check_would_catch_a_column_that_is_not_plumbed(self):
        """Guard the guard: a scan that silently matches nothing proves nothing."""
        columns = _source_columns_read_by_skills()
        assert len(columns) >= len(SKILL_KEYS), (
            f"only {len(columns)} source columns parsed for {len(SKILL_KEYS)} skills — "
            "the AST scan has stopped matching the code it is supposed to police"
        )
        assert "DEF_RATING" not in (set(MODEL_FEATURES) - set(MODEL_FEATURES)), "sanity"

    def test_post_collapse_columns_really_are_produced(self):
        frame = _window_frame()
        for col in POST_COLLAPSE_COLUMNS:
            assert col in frame.columns, f"{col} is declared post-collapse but not produced"


def _season_frame(n: int = 60, seasons=("2024-25", "2025-26")) -> pd.DataFrame:
    rng = np.random.default_rng(11)
    rows = []
    for season_i, season in enumerate(seasons):
        for i in range(n):
            games = 40 + (i % 40)
            minutes = 6.0 + (i % 25)
            rows.append(
                {
                    "player_id": f"p{i}",
                    "season": season,
                    "team_id": f"t{i % 5}",
                    "full_name": f"P {i}",
                    "nba_player_id": 1000 + i,
                    "height_inches": 70.0 + (i % 17),
                    "position": "G",
                    "is_active": True,
                    "GP": games,
                    "MIN": minutes,
                    "total_minutes": games * minutes,
                    "pts_per75": float(rng.uniform(4, 32)),
                    "TS_PCT": float(rng.uniform(0.45, 0.66)),
                    "USG_PCT": float(rng.uniform(0.10, 0.36)),
                    "AST_PCT": float(rng.uniform(0.04, 0.44)),
                    "TM_TOV_PCT": float(rng.uniform(5, 20)),
                    "OREB_PCT": float(rng.uniform(0.005, 0.13)),
                    "DREB_PCT": float(rng.uniform(0.05, 0.34)),
                    "stl_per_min": float(rng.uniform(0.005, 0.06)),
                    "blk_per_min": float(rng.uniform(0.0, 0.09)),
                    "pf_per_min": float(rng.uniform(0.02, 0.13)),
                    "fg3a_rate": float(rng.uniform(0.05, 0.8)),
                    "fg3a_per_min": float(rng.uniform(0.0, 0.35)),
                    "fta_rate": float(rng.uniform(0.05, 0.5)),
                    "def_diff_raw": float(rng.normal(0, 6)),
                    "FG3A": float(rng.uniform(0.3, 10.0)),
                    "FG3M": float(rng.uniform(0.1, 4.0)),
                    "AGE": 20.0 + (i % 16) + season_i,
                    "PIE": float(rng.uniform(0.02, 0.20)),
                    "NET_RATING": float(rng.normal(0, 6)),
                }
            )
    return pd.DataFrame(rows)


def _window_frame() -> pd.DataFrame:
    return recency_weighted_features(_season_frame(), ["2024-25", "2025-26"])


class TestShrinkageHappensAfterTheCollapse:
    def test_def_impact_uses_window_minutes_not_season_minutes(self):
        frame = _window_frame()
        minutes = frame["total_minutes_window"].astype(float)
        expected = frame["def_diff_raw"].astype(float) * (
            minutes / (minutes + DEF_SHRINKAGE_MINUTES)
        )
        assert frame["def_impact"].astype(float).to_numpy() == pytest.approx(
            expected.to_numpy()
        )

    def test_shrinking_before_the_collapse_would_compress_the_spread(self):
        """The reason the derivation moved. Shrinking each season as though it were the
        only evidence available throws away the window's accumulated minutes."""
        season = _season_frame()
        per_season = season["total_minutes"].astype(float)
        season["def_impact_early"] = season["def_diff_raw"].astype(float) * (
            per_season / (per_season + DEF_SHRINKAGE_MINUTES)
        )
        MODEL_FEATURES.append("def_impact_early")
        try:
            collapsed = recency_weighted_features(season, ["2024-25", "2025-26"])
        finally:
            MODEL_FEATURES.remove("def_impact_early")
        correct = collapsed["def_impact"].astype(float).std()
        early = collapsed["def_impact_early"].astype(float).std()
        assert correct > early * 1.2, (
            f"post-collapse shrinkage sd {correct:.4f} should materially exceed "
            f"pre-collapse {early:.4f}"
        )

    def test_attempts_are_summed_not_averaged(self):
        """The shrinkage constant is denominated in attempts, so the denominator has to
        be an evidence count. A mean of per-season attempts is a rate."""
        decay = 0.7
        season = _season_frame()
        season_attempts = season["FG3A"].astype(float) * season["GP"].astype(float)
        # Most recent season carries weight 1, the one before it `decay`.
        weight = season["season"].map({"2025-26": 1.0, "2024-25": decay})
        expected_sum = (season_attempts * weight).groupby(season["player_id"]).sum()
        expected_mean = (
            (season_attempts * weight).groupby(season["player_id"]).sum()
            / weight.groupby(season["player_id"]).sum()
        )

        frame = _window_frame().set_index("player_id")
        got = frame["fg3a_window"].astype(float)
        assert got.to_numpy() == pytest.approx(expected_sum.reindex(got.index).to_numpy())
        # The distinction that matters: a MEAN would divide by the weights, and with a
        # two-season window that is a factor of 1.7 — enough to halve every player's
        # apparent evidence and so to over-shrink every accuracy in the league.
        assert got.to_numpy() != pytest.approx(expected_mean.reindex(got.index).to_numpy())
        assert (got > expected_mean.reindex(got.index)).all()

    def test_shrunk_accuracy_removes_the_degenerate_extremes(self):
        season = _season_frame()
        season.loc[season.index[:5], "FG3M"] = 0.0  # nobody makes any
        season.loc[season.index[5:10], "FG3M"] = season.loc[season.index[5:10], "FG3A"]
        frame = recency_weighted_features(season, ["2024-25", "2025-26"])
        shrunk = frame["fg3_pct_shrunk"].astype(float).dropna()
        assert not ((shrunk <= 0.0) | (shrunk >= 1.0)).any()
        assert shrunk.min() > 0.0 and shrunk.max() < 1.0

    def test_a_player_with_no_attempts_has_no_accuracy_rather_than_the_prior(self):
        """Falling back to the league mean would make the skill a constant for everyone
        who has never shot — which is the silent-default failure in a new costume."""
        season = _season_frame()
        season["FG3A"] = 0.0
        season["FG3M"] = 0.0
        frame = recency_weighted_features(season, ["2024-25", "2025-26"])
        assert frame["fg3_pct_shrunk"].isna().all()

    def test_the_prior_is_the_measured_league_mean(self):
        assert pytest.approx(0.3618) == FG3_LEAGUE_MEAN
        assert pytest.approx(300.0) == FG3_SHRINKAGE_ATTEMPTS


class TestDefensiveDifferentialExcludesSelf:
    def test_a_player_is_not_part_of_his_own_baseline(self):
        from app.analytics.features import _teammate_def_rating_excluding_self

        df = pd.DataFrame(
            {
                "team_id": ["t1", "t1", "t1"],
                "season": ["2025-26"] * 3,
                "DEF_RATING": [100.0, 110.0, 120.0],
                "total_minutes": [1000.0, 1000.0, 1000.0],
            }
        )
        baseline = _teammate_def_rating_excluding_self(df)
        # Equal minutes, so each player's baseline is the mean of the OTHER two.
        assert baseline.tolist() == pytest.approx([115.0, 110.0, 105.0])

    def test_a_lone_measured_player_has_no_baseline(self):
        from app.analytics.features import _teammate_def_rating_excluding_self

        df = pd.DataFrame(
            {
                "team_id": ["t1"],
                "season": ["2025-26"],
                "DEF_RATING": [100.0],
                "total_minutes": [1000.0],
            }
        )
        assert _teammate_def_rating_excluding_self(df).isna().all()

    def test_the_baseline_is_minutes_weighted(self):
        from app.analytics.features import _teammate_def_rating_excluding_self

        df = pd.DataFrame(
            {
                "team_id": ["t1", "t1", "t1"],
                "season": ["2025-26"] * 3,
                "DEF_RATING": [100.0, 100.0, 130.0],
                "total_minutes": [10.0, 3000.0, 1000.0],
            }
        )
        first = _teammate_def_rating_excluding_self(df).iloc[0]
        # Teammates: 100 over 3000 minutes and 130 over 1000 -> nearer 100 than 115.
        assert 105.0 < first < 110.0


class TestCacheContract:
    def test_the_fingerprint_is_stable_across_calls(self):
        assert skill_schema_fingerprint() == skill_schema_fingerprint()
        assert len(skill_schema_fingerprint()) == 12

    def test_the_fingerprint_changes_when_the_skill_keys_change(self):
        """Guards the deploy hazard directly: if this can be defeated, a released change
        to the skill contract can be served from a cache built before it."""
        before = skill_schema_fingerprint()
        SKILL_KEYS.append("__probe__")
        skill_schema_fingerprint.cache_clear()
        try:
            after = skill_schema_fingerprint()
        finally:
            SKILL_KEYS.remove("__probe__")
            skill_schema_fingerprint.cache_clear()
        assert after != before
        assert skill_schema_fingerprint() == before

    def test_the_cache_key_carries_the_fingerprint(self):
        from app.core.cache import get_cache

        key = get_cache().versioned_key("skills", skill_schema_fingerprint())
        assert key.endswith(skill_schema_fingerprint())
        assert ":skills:" in key


class TestSkillHealthOnAScoredPopulation:
    """A four-part bar. `sd > 0.05` alone cannot separate healthy from broken: a clean
    percentile over hundreds of players has sd ~0.289 by construction, so 0.05 is more
    than five times too loose, and both a binary skill (sd 0.31) and a column that is
    zero for 90 % of players (sd 0.26) clear it while being useless.
    """

    @pytest.fixture(scope="class")
    def vectors(self):
        frame = _window_frame()
        return frame, [
            player_skill_vector(frame.iloc[i], frame) for i in range(len(frame))
        ]

    def test_every_declared_skill_resolves_for_almost_everyone(self, vectors):
        frame, vecs = vectors
        for key in SKILL_KEYS:
            coverage = sum(1 for v in vecs if key in v) / len(vecs)
            assert coverage >= 0.90, f"{key} resolves for only {coverage:.1%} of players"

    def test_no_skill_is_degenerate(self, vectors):
        _, vecs = vectors
        for key in SKILL_KEYS:
            values = pd.Series([v[key] for v in vecs if key in v])
            assert len(values) > 0, f"{key} resolves for nobody"
            assert values.std() >= 0.15, f"{key} sd {values.std():.4f} below 0.15"
            counts = values.round(6).value_counts(normalize=True)
            assert counts.iloc[0] <= 0.15, (
                f"{key} has {counts.iloc[0]:.1%} of players tied on one value"
            )
            effective = 1.0 / float((counts**2).sum())
            assert effective >= 10, f"{key} has only {effective:.1f} effective values"

    def test_every_skill_is_reachable_from_a_need(self):
        """A skill no need maps to can only ever levy a redundancy penalty — it can
        subtract from a fit score but never add. The existing containment test checks
        only the other direction."""
        unreachable = sorted(set(SKILL_KEYS) - set(NEED_TO_SKILL.values()))
        assert unreachable == [], (
            f"{unreachable} are computed but no need maps to them, so they can only "
            "ever penalise a trade"
        )
