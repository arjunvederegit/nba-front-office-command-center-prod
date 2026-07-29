"""R4-3 — deterministic size-first roles, and the degeneracy they replace.

Measured on the real 632-player window frame, k-means reached only 5 of its 10 label
branches, suffixed 217 of 632 rows with a disambiguating number, scored a silhouette of
0.154, and — the defect nothing previously measured — rewrote **65.7 %** of surviving
players' labels when a random 10 % of the population was dropped.

The rule chain is a total function of one row plus league cut points. These tests assert
the properties that makes true, because a role label is only useful if it is a property of
the player rather than of the run.
"""

import hashlib

import numpy as np
import pandas as pd
import pytest

from app.analytics.archetypes import (
    DISCRIMINANTS,
    MAX_MISSING_DISCRIMINANTS,
    REAL_ROLES,
    ROLE_ID,
    ROLE_ORDER,
    SIZE_FEATURE,
    UNCLASSIFIED_SIZE,
    UNCLASSIFIED_STATS,
    assign_role,
    fit_archetypes,
    league_thresholds,
)


def _frame(n: int = 400) -> pd.DataFrame:
    """A league with real spread on every discriminant, so every branch is reachable."""
    rng = np.random.default_rng(20260728)
    return pd.DataFrame(
        {
            "player_id": [f"p{i:04d}" for i in range(n)],
            "full_name": [f"Player {i}" for i in range(n)],
            "height_inches": rng.uniform(69.0, 87.0, n),
            "USG_PCT": rng.uniform(0.08, 0.40, n),
            "AST_PCT": rng.uniform(0.03, 0.50, n),
            "fg3a_rate": rng.uniform(0.0, 0.85, n),
            "stl_per_min": rng.uniform(0.0, 0.07, n),
            "blk_per_min": rng.uniform(0.0, 0.10, n),
            "OREB_PCT": rng.uniform(0.002, 0.16, n),
            "total_minutes_window": rng.uniform(200.0, 7000.0, n),
        }
    )


def _digest(frame: pd.DataFrame) -> str:
    return hashlib.sha256(
        frame[["player_id", "role_id", "label"]].to_csv(index=False).encode()
    ).hexdigest()


class TestNonDegeneracy:
    """The seven tests, on a synthetic league. Real-frame numbers are in the release
    report; these keep the properties from regressing without needing a database."""

    @pytest.fixture(scope="class")
    def assigned(self):
        frame = _frame()
        return frame, *fit_archetypes(frame)

    def test_i_every_real_role_fires(self, assigned):
        _, out, _ = assigned
        missing = sorted(set(REAL_ROLES) - set(out.label))
        assert missing == [], f"branches never reached: {missing}"

    def test_ii_no_role_dominates(self, assigned):
        _, out, meta = assigned
        assert meta["max_share"] < 0.20, f"largest role holds {meta['max_share']:.1%}"

    def test_iii_no_real_role_is_vestigial(self, assigned):
        _, out, _ = assigned
        counts = out[out.label.isin(REAL_ROLES)].label.value_counts()
        assert counts.min() / len(out) > 0.01

    def test_iv_no_label_carries_a_numeric_suffix(self, assigned):
        """k-means produced `primary creator (2)` for 217 of 632 real rows, which is a
        counter, not a basketball role."""
        _, out, _ = assigned
        offenders = [lbl for lbl in set(out.label) if lbl.rstrip(")").rstrip("0123456789").endswith(" (")]
        assert offenders == []

    def test_v_the_distribution_is_not_concentrated(self, assigned):
        _, _, meta = assigned
        assert meta["herfindahl"] < 0.15

    def test_vi_output_is_byte_identical_across_runs_and_row_order(self, assigned):
        frame, out, _ = assigned
        again, _ = fit_archetypes(frame)
        assert _digest(out) == _digest(again)
        shuffled, _ = fit_archetypes(frame.sample(frac=1.0, random_state=3))
        assert _digest(out) == _digest(
            shuffled.sort_values("player_id", kind="mergesort").reset_index(drop=True)
        )

    def test_vii_labels_barely_move_when_the_population_does(self, assigned):
        """The decisive k-means failure: 65.7 % churn under a 10 % drop. A label that
        changes two times in three is a property of the run, not of the player."""
        frame, out, _ = assigned
        rng = np.random.default_rng(11)
        churn = []
        for _ in range(20):
            keep = np.sort(rng.choice(len(frame), size=int(len(frame) * 0.9), replace=False))
            sub_out, _ = fit_archetypes(frame.iloc[keep])
            before = out.set_index("player_id").label.reindex(sub_out.player_id).to_numpy()
            churn.append(float((before != sub_out.label.to_numpy()).mean()))
        assert np.mean(churn) < 0.10, f"mean churn {np.mean(churn):.3f}"


class TestSizeGatesFirst:
    def test_a_tall_high_assist_player_is_a_big_not_a_creator(self):
        """The measured failure of a creation-first chain: it labelled Wembanyama a
        secondary creator. Height constrains the available roles before skill does."""
        frame = _frame()
        thresholds = league_thresholds(frame)
        giant = pd.Series(
            {
                "height_inches": 90.0,
                "USG_PCT": 0.34,
                "AST_PCT": 0.40,
                "fg3a_rate": 0.10,
                "stl_per_min": 0.03,
                "blk_per_min": 0.09,
                "OREB_PCT": 0.09,
            }
        )
        assert assign_role(giant, thresholds).endswith("big")

    def test_a_short_high_assist_player_is_a_guard(self):
        frame = _frame()
        thresholds = league_thresholds(frame)
        small = pd.Series(
            {
                "height_inches": 70.0,
                "USG_PCT": 0.30,
                "AST_PCT": 0.48,
                "fg3a_rate": 0.45,
                "stl_per_min": 0.03,
                "blk_per_min": 0.002,
                "OREB_PCT": 0.01,
            }
        )
        assert assign_role(small, thresholds) == "lead guard"


class TestMissingDataIsVisible:
    def test_a_player_with_no_height_is_labelled_unclassified_not_guessed(self):
        """k-means filled the league median and produced a confident role for 49 players
        (7.75 %) whose height nobody recorded."""
        frame = _frame()
        thresholds = league_thresholds(frame)
        row = frame.iloc[5].copy()
        row[SIZE_FEATURE] = None
        assert assign_role(row, thresholds) == UNCLASSIFIED_SIZE

    def test_too_many_missing_discriminants_is_its_own_label(self):
        frame = _frame()
        thresholds = league_thresholds(frame)
        row = frame.iloc[5].copy()
        for col in DISCRIMINANTS[: MAX_MISSING_DISCRIMINANTS + 1]:
            row[col] = None
        assert assign_role(row, thresholds) == UNCLASSIFIED_STATS

    def test_a_few_missing_discriminants_still_yields_a_real_role(self):
        frame = _frame()
        thresholds = league_thresholds(frame)
        row = frame.iloc[5].copy()
        for col in DISCRIMINANTS[:MAX_MISSING_DISCRIMINANTS]:
            row[col] = None
        assert assign_role(row, thresholds) in REAL_ROLES

    def test_a_thin_column_narrows_the_chain_rather_than_passing_silently(self):
        """Fewer than 30 observations means no cut point, and every branch reading that
        column must then evaluate False — not pass on a cut built from a handful."""
        frame = _frame()
        frame.loc[frame.index[20:], "blk_per_min"] = None
        thresholds = league_thresholds(frame)
        assert "blk_per_min" not in thresholds
        out, _ = fit_archetypes(frame)
        assert "rim-protecting big" not in set(out.label)
        assert not out.empty


class TestThresholdsTrackTheLeague:
    def test_cut_points_are_percentiles_not_magic_numbers(self):
        """Scaling a whole column must not reshuffle anyone: the cuts move with it."""
        frame = _frame()
        before, _ = fit_archetypes(frame)
        scaled = frame.copy()
        scaled["fg3a_rate"] = scaled["fg3a_rate"] * 1.25
        after, _ = fit_archetypes(scaled)
        assert before.label.tolist() == after.label.tolist()

    def test_thresholds_are_reported_in_the_metadata(self):
        _, meta = fit_archetypes(_frame())
        assert set(meta["thresholds"]) <= {"height_inches", *DISCRIMINANTS}
        assert meta["method"].startswith("size-first")
        assert "silhouette" not in meta


class TestRoleIdContract:
    def test_ids_are_unique_and_stable(self):
        assert len(set(ROLE_ID.values())) == len(ROLE_ID)

    def test_every_label_the_chain_can_emit_has_an_id(self):
        out, _ = fit_archetypes(_frame())
        assert set(out.label) <= set(ROLE_ID)

    def test_role_order_matches_the_id_map(self):
        assert [r for r, _ in sorted(ROLE_ID.items(), key=lambda kv: kv[1])] == ROLE_ORDER

    def test_unclassified_ids_sit_outside_the_real_role_range(self):
        """So a numeric filter for real roles cannot accidentally include them."""
        assert min(ROLE_ID[u] for u in (UNCLASSIFIED_SIZE, UNCLASSIFIED_STATS)) > max(
            ROLE_ID[r] for r in REAL_ROLES
        )


class TestEdgeCases:
    def test_an_empty_frame_returns_empty_rather_than_raising(self):
        out, meta = fit_archetypes(pd.DataFrame())
        assert out.empty
        assert "note" in meta

    def test_a_tiny_league_still_labels_everyone(self):
        """Under 30 rows there are no cut points at all, so nothing can be discriminated
        — but every player must still receive a label."""
        out, _ = fit_archetypes(_frame(12))
        assert len(out) == 12
        assert out.label.notna().all()

    def test_identical_rows_receive_identical_labels(self):
        """The chain is a function of the row: same inputs, same role, every time —
        including for players sitting exactly on a cut point, where an exclusive
        comparison would split them arbitrarily."""
        frame = _frame()
        thresholds = league_thresholds(frame)
        # Place a cohort exactly ON several league cut points at once.
        cohort = frame.iloc[:40].copy()
        for col in ("height_inches", "fg3a_rate", "USG_PCT", "AST_PCT", "stl_per_min",
                    "blk_per_min", "OREB_PCT"):
            cohort[col] = thresholds[col][75] if col in thresholds else 0.0
        frame.iloc[:40] = cohort
        out, _ = fit_archetypes(frame)
        tied = out[out.player_id.isin(frame.player_id[:40])]
        assert tied.label.nunique() == 1, (
            f"identical rows split across {sorted(set(tied.label))}"
        )
