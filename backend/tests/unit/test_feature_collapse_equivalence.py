"""R5-4. The vectorised window collapse must equal the loop it replaced.

`recency_weighted_features` was the measured cold-cache hotspot of the whole request path
at **1.045 s**: it ran `pd.to_numeric` and `np.average` once per (player, column) — 632 ×
19 calls, each rebuilding a Series and a boolean mask. Rewritten as grouped arithmetic it
takes **0.045 s**, a 23.6× speedup, and on the real 1,714-row feature frame every one of
the 33 output columns matches to **9.1e-13** — float summation order on a sum of minutes,
nothing else.

A speedup that changes a number is not a speedup, so the loop lives on here as the oracle.
The cases below are the ones where "weighted mean of the present values" and "sum of
weighted values over sum of weights" can come apart: a column missing for some seasons but
not others, a player observed once, a zero-minute season, a column missing for everyone.
"""

from typing import Any

import numpy as np
import pandas as pd
import pytest

from app.analytics.features import (
    MODEL_FEATURES,
    _derive_post_collapse,
    recency_weighted_features,
)

SEASONS = ["2023-24", "2024-25", "2025-26"]


def legacy_collapse(
    df: pd.DataFrame, seasons: list[str], decay: float = 0.7, min_total_minutes: float = 200.0
) -> pd.DataFrame:
    """The pre-R5-4 implementation, verbatim in behaviour. The oracle, not the product."""
    ordered = list(reversed(seasons))
    weight_by_season = {season: decay**i for i, season in enumerate(ordered)}
    df = df[df["season"].isin(seasons)].copy()
    df["season_w"] = df["season"].map(weight_by_season).astype(float)
    df["recency_w"] = df["season_w"] * df["total_minutes"].astype(float)

    def recency_sum(group: pd.DataFrame, per_game_col: str) -> float:
        if per_game_col not in group.columns or "GP" not in group.columns:
            return float("nan")
        total = (
            pd.to_numeric(group[per_game_col], errors="coerce")
            * pd.to_numeric(group["GP"], errors="coerce")
            * group["season_w"].astype(float)
        )
        return float(total.sum()) if total.notna().any() else float("nan")

    numeric_cols = [c for c in MODEL_FEATURES if c in df.columns]
    records: list[dict[str, Any]] = []
    for player_id, group in df.groupby("player_id"):
        weights = group["recency_w"].astype(float)
        if weights.sum() <= 0 or group["total_minutes"].sum() < min_total_minutes:
            continue
        latest = group.sort_values("season").iloc[-1]
        record: dict[str, Any] = {
            "player_id": player_id,
            "full_name": latest["full_name"],
            "nba_player_id": latest["nba_player_id"],
            "height_inches": latest["height_inches"],
            "position": latest["position"],
            "is_active": latest["is_active"],
            "latest_season": latest["season"],
            "seasons_observed": len(group),
            "total_minutes_window": float(group["total_minutes"].sum()),
            "fg3a_window": recency_sum(group, "FG3A"),
            "fg3m_window": recency_sum(group, "FG3M"),
        }
        for col in numeric_cols:
            values = pd.to_numeric(group[col], errors="coerce")
            mask = values.notna()
            record[col] = (
                float(np.average(values[mask], weights=weights[mask])) if mask.any() else None
            )
        records.append(record)
    window = pd.DataFrame(records)
    if window.empty:
        return window
    return _derive_post_collapse(window)


def _frame(rows: list[dict]) -> pd.DataFrame:
    base = {
        "full_name": "Player",
        "nba_player_id": 1,
        "height_inches": 78,
        "position": "G",
        "is_active": True,
        "GP": 70,
    }
    frame = pd.DataFrame([{**base, **row} for row in rows])
    for col in MODEL_FEATURES:
        if col not in frame.columns:
            frame[col] = np.nan
    return frame


def assert_equivalent(frame: pd.DataFrame) -> pd.DataFrame:
    old = legacy_collapse(frame.copy(), SEASONS)
    new = recency_weighted_features(frame.copy(), SEASONS)
    if old.empty:
        assert new.empty
        return new
    old = old.set_index("player_id").sort_index()
    new = new.set_index("player_id").sort_index()
    assert list(old.index) == list(new.index)
    assert set(old.columns) == set(new.columns)
    for col in old.columns:
        a = pd.to_numeric(old[col], errors="coerce")
        b = pd.to_numeric(new[col], errors="coerce")
        if a.notna().any() or b.notna().any():
            av, bv = a.to_numpy(float), b.to_numpy(float)
            both_nan = np.isnan(av) & np.isnan(bv)
            assert (both_nan | (np.abs(av - bv) < 1e-9)).all(), f"{col} differs"
        else:
            assert (old[col].fillna("~") == new[col].fillna("~")).all(), f"{col} differs"
    return new


class TestEquivalence:
    def test_a_plain_three_season_player(self):
        frame = _frame(
            [
                {"player_id": "p1", "season": s, "total_minutes": m, "MIN": 30.0, "PIE": v}
                for s, m, v in zip(SEASONS, (1800.0, 2000.0, 2200.0), (0.10, 0.12, 0.14), strict=False)
            ]
        )
        window = assert_equivalent(frame)
        assert len(window) == 1

    def test_a_column_present_in_only_one_season(self):
        """The case that separates 'mean of present values' from 'sum over sum': the
        denominator must exclude the seasons where the column is missing."""
        rows = [
            {"player_id": "p1", "season": s, "total_minutes": m, "MIN": 30.0}
            for s, m in zip(SEASONS, (1800.0, 2000.0, 2200.0), strict=False)
        ]
        rows[1]["PIE"] = 0.20
        frame = _frame(rows)
        window = assert_equivalent(frame)
        assert window["PIE"].iloc[0] == pytest.approx(0.20)

    def test_a_column_missing_for_everyone_stays_missing(self):
        frame = _frame(
            [
                {"player_id": "p1", "season": s, "total_minutes": 1000.0, "MIN": 25.0}
                for s in SEASONS
            ]
        )
        window = assert_equivalent(frame)
        assert window["PIE"].isna().all()

    def test_a_single_season_player(self):
        frame = _frame(
            [{"player_id": "p1", "season": "2025-26", "total_minutes": 900.0, "MIN": 20.0, "PIE": 0.1}]
        )
        window = assert_equivalent(frame)
        assert window["seasons_observed"].iloc[0] == 1

    def test_a_zero_minute_season_contributes_no_weight(self):
        frame = _frame(
            [
                {"player_id": "p1", "season": "2023-24", "total_minutes": 0.0, "MIN": 0.0, "PIE": 99.0},
                {"player_id": "p1", "season": "2025-26", "total_minutes": 1500.0, "MIN": 30.0, "PIE": 0.10},
            ]
        )
        window = assert_equivalent(frame)
        assert window["PIE"].iloc[0] == pytest.approx(0.10)

    def test_players_below_the_minute_floor_are_dropped(self):
        frame = _frame(
            [
                {"player_id": "thin", "season": "2025-26", "total_minutes": 100.0, "MIN": 5.0, "PIE": 0.1},
                {"player_id": "thick", "season": "2025-26", "total_minutes": 1500.0, "MIN": 30.0, "PIE": 0.1},
            ]
        )
        window = assert_equivalent(frame)
        assert list(window.index) == ["thick"]

    def test_an_all_thin_frame_returns_empty(self):
        frame = _frame(
            [{"player_id": "thin", "season": "2025-26", "total_minutes": 10.0, "MIN": 1.0}]
        )
        assert assert_equivalent(frame).empty

    def test_a_ragged_population(self):
        """Many players, different season counts, scattered missing values — the shape the
        real frame has."""
        rng = np.random.default_rng(20260812)
        rows = []
        for i in range(60):
            for season in SEASONS[: 1 + (i % 3)]:
                row = {
                    "player_id": f"p{i}",
                    "season": season,
                    "total_minutes": float(rng.uniform(150, 2600)),
                    "MIN": float(rng.uniform(5, 36)),
                    "GP": int(rng.integers(10, 82)),
                }
                for col in ("PIE", "TS_PCT", "USG_PCT", "AST_PCT", "FG3A", "FG3M"):
                    if rng.random() > 0.25:
                        row[col] = float(rng.uniform(0.0, 5.0))
                rows.append(row)
        window = assert_equivalent(_frame(rows))
        assert len(window) > 20

    def test_the_latest_season_columns_come_from_the_latest_row(self):
        frame = _frame(
            [
                {
                    "player_id": "p1",
                    "season": "2023-24",
                    "total_minutes": 1000.0,
                    "MIN": 25.0,
                    "position": "G",
                    "height_inches": 74,
                },
                {
                    "player_id": "p1",
                    "season": "2025-26",
                    "total_minutes": 1000.0,
                    "MIN": 25.0,
                    "position": "F",
                    "height_inches": 79,
                },
            ]
        )
        window = assert_equivalent(frame)
        assert window["position"].iloc[0] == "F"
        assert window["height_inches"].iloc[0] == 79
        assert window["latest_season"].iloc[0] == "2025-26"
