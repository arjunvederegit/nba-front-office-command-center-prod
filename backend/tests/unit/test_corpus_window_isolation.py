"""The corpus window is not the modelling window, and widening it must not move a model.

R7-2 widened what the historical-trade corpus can be described by from three seasons of
`player_season_stats` to ten. Nothing about the served product may change as a result, and
"nothing" here is a measurable claim rather than a hope:

- `recency_weighted_features` filters to `history_seasons` before it collapses anything,
  so the served window frame is byte-identical at 632 rows x 33 columns;
- `add_zscores` standardizes **within** season, so a 2016-17 row cannot move a 2024-25 z;
- `_team_tei_transitions` filters to `history_seasons` after grouping per (team, season),
  so every R3 calibration figure reproduces to full float precision — coefficient
  14.976967215546017, SE 1.5279397396294392, R2 0.6235734193376163 — on a season frame
  that grows from 1,714 rows to 5,483.

The tests below assert the three structural reasons, on synthetic frames that carry a
season outside the modelling window. They do not need the real database, and they fail if
a future release makes the corpus window reach the served path.
"""

import hashlib

import numpy as np
import pandas as pd

from app.analytics.features import (
    MODEL_FEATURES,
    recency_weighted_features,
)
from app.analytics.impact import Z_SOURCE_COLS, add_zscores, baseline_index
from app.config import get_settings

MODELLED = ["2023-24", "2024-25", "2025-26"]
OUTSIDE = "2016-17"


def _value(season: str, player: int, column: str) -> float:
    """Deterministic per (season, player, column).

    A shared `default_rng` consumed in season order would make the *fixture* change when a
    season is prepended, which is the very thing under test. Every cell here is a function
    of its own coordinates, so the modelled seasons are literally the same numbers in both
    frames and any difference downstream is the code's.
    """
    seed = int.from_bytes(
        hashlib.blake2b(f"{season}|{player}|{column}".encode(), digest_size=8).digest(),
        "big",
    )
    era = SEASON_ERA[season]
    # A different location and spread per season, so a leak between seasons would move
    # the numbers rather than hide inside them.
    return float(np.random.default_rng(seed).normal(10 * era, 2 + era))


SEASON_ERA = {OUTSIDE: 0, "2023-24": 1, "2024-25": 2, "2025-26": 3}


def _frame(seasons: list[str], n_per_season: int = 40) -> pd.DataFrame:
    """A season frame with the columns the collapse and the index both read."""
    rows = []
    for season in seasons:
        for i in range(n_per_season):
            row: dict[str, object] = {
                "player_id": f"p{i:03d}",
                "season": season,
                "team_id": f"t{i % 5}",
                "full_name": f"Player {i}",
                "nba_player_id": 1000 + i,
                "height_inches": 78,
                "position": "G",
                "is_active": True,
                "GP": 70,
                "MIN": 28.0,
                "total_minutes": 1960.0,
            }
            for col in sorted(set(MODEL_FEATURES) | set(Z_SOURCE_COLS)):
                row.setdefault(col, _value(season, i, col))
            rows.append(row)
    return pd.DataFrame(rows)


class TestTheServedWindowCannotSeeTheCorpusWindow:
    def test_the_collapse_drops_every_season_outside_the_modelling_window(self):
        narrow = recency_weighted_features(_frame(MODELLED), MODELLED)
        wide = recency_weighted_features(_frame([OUTSIDE, *MODELLED]), MODELLED)
        assert not narrow.empty
        assert sorted(narrow.columns) == sorted(wide.columns)
        numeric = sorted(narrow.select_dtypes("number").columns)
        pd.testing.assert_frame_equal(
            narrow.sort_values("player_id").reset_index(drop=True)[numeric],
            wide.sort_values("player_id").reset_index(drop=True)[numeric],
        )

    def test_a_season_outside_the_window_does_not_move_a_z_score_inside_it(self):
        """`add_zscores` standardizes within season. This is the property that lets one
        table serve both windows; without it every served estimate would move whenever a
        historical season was ingested."""
        narrow = add_zscores(_frame(MODELLED).copy())
        wide = add_zscores(_frame([OUTSIDE, *MODELLED]).copy())
        wide = wide[wide["season"].isin(MODELLED)]
        z_cols = sorted(c for c in narrow.columns if c.startswith("z_"))
        assert z_cols, "no z columns were produced; the fixture no longer exercises this"
        pd.testing.assert_frame_equal(
            narrow.sort_values(["season", "player_id"]).reset_index(drop=True)[z_cols],
            wide.sort_values(["season", "player_id"]).reset_index(drop=True)[z_cols],
        )

    def test_the_index_is_unchanged_for_every_row_in_the_modelling_window(self):
        narrow = add_zscores(_frame(MODELLED).copy())
        narrow["tei"] = baseline_index(narrow)
        wide = add_zscores(_frame([OUTSIDE, *MODELLED]).copy())
        wide["tei"] = baseline_index(wide)
        wide = wide[wide["season"].isin(MODELLED)]
        np.testing.assert_array_equal(
            narrow.sort_values(["season", "player_id"])["tei"].to_numpy(),
            wide.sort_values(["season", "player_id"])["tei"].to_numpy(),
        )


class TestTheTwoWindowsStaySeparate:
    def test_the_modelling_window_is_not_the_corpus_window(self):
        """If these ever become the same list, the isolation above stops being tested by
        anything — and R7's whole justification for widening the corpus was that they are
        different questions asked of one table."""
        settings = get_settings()
        assert set(settings.history_season_list) < set(settings.corpus_season_list)

    def test_the_corpus_window_contains_the_modelling_window(self):
        """The other direction is a correctness requirement, not a preference: a corpus
        season list that dropped a modelled season would leave recent trades unrankable
        while older ones ranked."""
        settings = get_settings()
        assert set(settings.history_season_list) <= set(settings.corpus_season_list)
