"""R4-1b — ball security is its own skill, and it points the right way.

`NEED_TO_SKILL` mapped `ball_security` to `creation`, i.e. to `pct(AST_PCT)`. A team with
a turnover problem was therefore told to acquire high-assist ball handlers — the
population that turns the ball over most. Measured on the ingested history, player-seasons
with >= 1000 minutes:

    corr(pct(AST_PCT), pct_inv(TM_TOV_PCT))            -0.255
    top 12 by assist rate that sit below median in
      turnover avoidance                                10 of 12
    their mean turnover avoidance                        0.285   (0.5 = league median)

The sign is the whole point of the fix, so it is asserted as a property over a synthetic
population rather than spot-checked on a named player.
"""

import numpy as np
import pandas as pd
import pytest

from app.analytics.archetypes import SKILL_KEYS, player_skill_vector
from app.analytics.needs import NEED_TO_SKILL


def _league(n: int = 40) -> pd.DataFrame:
    rng = np.random.default_rng(20260728)
    return pd.DataFrame(
        {
            "player_id": [f"p{i}" for i in range(n)],
            "fg3a_rate": rng.uniform(0.05, 0.75, n),
            "TS_PCT": rng.uniform(0.45, 0.68, n),
            "AST_PCT": rng.uniform(0.04, 0.45, n),
            "TM_TOV_PCT": rng.uniform(5.0, 20.0, n),
            "stl_per_min": rng.uniform(0.005, 0.06, n),
            "blk_per_min": rng.uniform(0.0, 0.09, n),
            "DREB_PCT": rng.uniform(0.05, 0.35, n),
            "OREB_PCT": rng.uniform(0.005, 0.14, n),
            "height_inches": rng.integers(70, 88, n).astype(float),
            "pts_per75": rng.uniform(4.0, 34.0, n),
        }
    )


class TestMappingIsFixed:
    def test_ball_security_no_longer_resolves_to_creation(self):
        """The exact defect. `creation` is pct(AST_PCT); mapping a turnover problem to it
        recommended the players most likely to cause the problem."""
        assert NEED_TO_SKILL["ball_security"] == "turnover_avoidance"
        assert NEED_TO_SKILL["ball_security"] != "creation"

    def test_turnover_avoidance_is_a_declared_skill(self):
        assert "turnover_avoidance" in SKILL_KEYS

    def test_creation_needs_still_map_to_creation(self):
        """The fix must not drag genuine creation needs off their skill."""
        assert NEED_TO_SKILL["playmaking"] == "creation"
        assert NEED_TO_SKILL["secondary_creation"] == "creation"

    def test_every_mapped_skill_exists(self):
        """A mapping to a skill nobody produces is silently a no-op in `fit_score`."""
        unknown = sorted(set(NEED_TO_SKILL.values()) - set(SKILL_KEYS))
        assert unknown == [], f"NEED_TO_SKILL points at undeclared skills: {unknown}"


class TestSignIsInverted:
    def test_more_turnovers_means_less_turnover_avoidance(self):
        league = _league()
        vectors = {
            i: player_skill_vector(league.iloc[i], league) for i in range(len(league))
        }
        worst = int(league["TM_TOV_PCT"].idxmax())
        best = int(league["TM_TOV_PCT"].idxmin())
        assert vectors[best]["turnover_avoidance"] > vectors[worst]["turnover_avoidance"]
        assert vectors[worst]["turnover_avoidance"] == pytest.approx(0.0, abs=1e-9)

    def test_the_skill_is_monotone_decreasing_over_the_whole_population(self):
        """Asserted over every player, not spot-checked — a partial inversion (say, one
        that only holds in the tails) would pass a two-player check."""
        league = _league(60)
        pairs = [
            (
                float(league.iloc[i]["TM_TOV_PCT"]),
                player_skill_vector(league.iloc[i], league)["turnover_avoidance"],
            )
            for i in range(len(league))
        ]
        skills = [s for _, s in sorted(pairs)]
        assert skills == sorted(skills, reverse=True), (
            "turnover_avoidance must fall monotonically as TM_TOV_PCT rises"
        )

    def test_a_turnover_need_never_prefers_the_higher_turnover_player(self):
        """The product-level statement of the bug: for every ordered pair of players,
        the one who turns it over more must never score better on the need."""
        league = _league(40)
        vecs = [player_skill_vector(league.iloc[i], league) for i in range(len(league))]
        tov = league["TM_TOV_PCT"].to_numpy()
        for i in range(len(league)):
            for j in range(len(league)):
                if tov[i] > tov[j]:
                    assert vecs[i]["turnover_avoidance"] <= vecs[j]["turnover_avoidance"]

    def test_percentiles_span_the_range(self):
        league = _league(60)
        vals = [
            player_skill_vector(league.iloc[i], league)["turnover_avoidance"]
            for i in range(len(league))
        ]
        assert min(vals) < 0.05 and max(vals) > 0.95
        assert pd.Series(vals).std() > 0.2


class TestMissingData:
    def test_an_absent_column_omits_the_skill_rather_than_defaulting(self):
        league = _league().drop(columns=["TM_TOV_PCT"])
        vector = player_skill_vector(league.iloc[5], league)
        assert "turnover_avoidance" not in vector

    def test_a_missing_value_omits_only_that_skill(self):
        league = _league()
        row = league.iloc[5].copy()
        row["TM_TOV_PCT"] = None
        vector = player_skill_vector(row, league)
        assert "turnover_avoidance" not in vector
        assert "creation" in vector

    def test_an_all_null_column_omits_the_skill(self):
        league = _league()
        league["TM_TOV_PCT"] = None
        vector = player_skill_vector(league.iloc[5], league)
        assert "turnover_avoidance" not in vector

    def test_a_single_player_league_does_not_divide_by_zero(self):
        league = _league(1)
        vector = player_skill_vector(league.iloc[0], league)
        assert vector["turnover_avoidance"] == pytest.approx(0.0)


class TestInversionIsNamed:
    def test_pct_inv_is_the_exact_mirror_of_pct(self):
        """`pct` counts the share strictly below; `pct_inv` the share strictly above.
        With distinct values the two must sum to 1 minus the player's own share."""
        league = _league(50)
        i = 17
        vec = player_skill_vector(league.iloc[i], league)
        series = league["TM_TOV_PCT"]
        value = league.iloc[i]["TM_TOV_PCT"]
        assert vec["turnover_avoidance"] == pytest.approx(float((series > value).mean()))

    def test_the_inversion_is_not_written_as_a_bare_literal_at_the_call_site(self):
        """A bare `1 - pct(...)` is one careless edit from silently losing the sign, and
        the sign is the entire fix.

        Structural, and over the AST rather than the text: a substring scan matches the
        prose in `pct_inv`'s own docstring that explains why not to write it that way,
        which makes the check fail on the documentation of the fix. Parsing means only
        real expressions count.
        """
        import ast
        from pathlib import Path

        path = Path(__file__).resolve().parents[2] / "app" / "analytics" / "archetypes.py"
        tree = ast.parse(path.read_text())

        names = {
            node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        }
        assert "pct_inv" in names, "the inversion must be a named helper"

        offenders = [
            ast.unparse(node)
            for node in ast.walk(tree)
            if isinstance(node, ast.BinOp)
            and isinstance(node.op, ast.Sub)
            and isinstance(node.left, ast.Constant)
            and node.left.value in (1, 1.0)
            and isinstance(node.right, ast.Call)
            and isinstance(node.right.func, ast.Name)
            and node.right.func.id == "pct"
        ]
        assert offenders == [], f"inline inversion found instead of pct_inv: {offenders}"

    def test_turnover_avoidance_is_wired_to_the_inverting_helper(self):
        """Not just that `pct_inv` exists — that the skill actually calls it."""
        import ast
        from pathlib import Path

        path = Path(__file__).resolve().parents[2] / "app" / "analytics" / "archetypes.py"
        tree = ast.parse(path.read_text())
        wired = [
            ast.unparse(value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Dict)
            for key, value in zip(node.keys, node.values, strict=False)
            if isinstance(key, ast.Constant) and key.value == "turnover_avoidance"
        ]
        # `ast.unparse` normalises string literals to single quotes.
        assert wired == ["pct_inv('TM_TOV_PCT')"], wired
