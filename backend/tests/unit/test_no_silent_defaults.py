"""Invariant: a default is never rendered as a measurement.

Two complementary checks.

1. **Behavioural** — the skill vector omits what it cannot measure, rather than
   returning 0.5. This is the C7 trap: `pct()` used to return 0.5 for a column that is
   not in the frame at all, *before ever touching the league series*, so a skill defined
   on an absent column silently became exactly 0.5 for every player — no error, no
   warning, no test failure, and the UI would report the need as addressed.

2. **Structural** — a source-level scan for the specific literal-fallback shapes that
   produced the audit's findings, so a new one cannot be added quietly. It is a grep,
   and a grep is blunt; every allowance is listed with its reason rather than the
   pattern being loosened.
"""

import ast
from pathlib import Path

import pandas as pd
import pytest

from app.analytics.archetypes import SKILL_KEYS, player_skill_vector

APP = Path(__file__).resolve().parents[2] / "app"

# Modules whose output can reach a rendered number.
#
# This list is literal paths, so a module that moves or is added is silently NOT scanned
# — the guard would keep passing over the old files while new scoring logic went
# unchecked. Anything that applies a threshold or serves a percentile belongs here.
SCANNED = [
    APP / "analytics" / "archetypes.py",
    APP / "analytics" / "fit.py",
    APP / "analytics" / "sensitivity.py",
    APP / "services" / "evaluation.py",
    # Pivot: serves skill percentiles, roster skill coverage and the fit component, and
    # applies the strength/weakness thresholds that used to live in the browser.
    APP / "services" / "intelligence.py",
]


def test_every_scanned_module_exists():
    """The scan is parametrized over literal paths, so a renamed module would make it
    silently vacuous rather than red. Fail loudly instead."""
    missing = [p for p in SCANNED if not p.exists()]
    assert missing == [], f"scanned modules that no longer exist: {missing}"


def _league_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "player_id": [f"p{i}" for i in range(20)],
            "fg3a_rate": [0.1 + i * 0.02 for i in range(20)],
            "TS_PCT": [0.48 + i * 0.005 for i in range(20)],
            "AST_PCT": [0.05 + i * 0.01 for i in range(20)],
            # Ascending, like every other column here, so a skill built on it is easy to
            # reason about — but this one is INVERTED into `turnover_avoidance`, so the
            # highest value must produce the *lowest* skill percentile.
            "TM_TOV_PCT": [6.0 + i * 0.4 for i in range(20)],
            "stl_per_min": [0.01 + i * 0.002 for i in range(20)],
            "blk_per_min": [0.005 + i * 0.003 for i in range(20)],
            "DREB_PCT": [0.08 + i * 0.01 for i in range(20)],
            "OREB_PCT": [0.01 + i * 0.004 for i in range(20)],
            "height_inches": [72 + i % 12 for i in range(20)],
            "pts_per75": [8.0 + i * 0.9 for i in range(20)],
            # R4 inputs. The two `*_score` columns are composites derived after the
            # recency collapse in `features._derive_post_collapse`; a fixture stands in
            # for them directly, because what this file tests is what happens to a skill
            # when its source column is present or absent, not how the source is built.
            "fg3a_per_min": [0.02 + i * 0.014 for i in range(20)],
            "fg3_pct_shrunk": [0.31 + i * 0.004 for i in range(20)],
            "team_defense_score": [-1.2 + i * 0.13 for i in range(20)],
        }
    )


# ------------------------------------------------------------------- behavioural


def test_skill_vector_is_complete_when_every_input_is_present() -> None:
    league = _league_frame()
    vector = player_skill_vector(league.iloc[10], league)
    assert set(vector) == set(SKILL_KEYS)
    assert all(0.0 <= v <= 1.0 for v in vector.values())


def test_a_missing_column_omits_the_skill_instead_of_returning_half() -> None:
    """The C7 trap, asserted directly."""
    league = _league_frame().drop(columns=["blk_per_min", "team_defense_score"])
    vector = player_skill_vector(league.iloc[10], league)
    assert "rim_protection" not in vector
    assert "team_defense" not in vector
    # the rest still resolve, from their own columns
    assert {
        "shooting_volume",
        "shooting_accuracy",
        "creation",
        "turnover_avoidance",
        "rebounding",
        "size",
        "scoring",
    } <= set(vector)


def test_a_missing_value_for_one_player_omits_only_that_skill() -> None:
    league = _league_frame()
    row = league.iloc[10].copy()
    row["AST_PCT"] = None
    vector = player_skill_vector(row, league)
    assert "creation" not in vector
    assert "scoring" in vector


def test_a_blend_renormalizes_over_the_components_that_exist() -> None:
    """`shooting_accuracy` is 0.7·fg3_pct_shrunk + 0.3·TS_PCT. With one part absent the
    other must carry the skill on its own, not be scaled toward zero by the missing
    weight."""
    league = _league_frame().drop(columns=["fg3_pct_shrunk"])
    vector = player_skill_vector(league.iloc[10], league)
    ts_only = float((pd.to_numeric(league["TS_PCT"]) < league.iloc[10]["TS_PCT"]).mean())
    assert vector["shooting_accuracy"] == pytest.approx(ts_only)


def test_no_skill_is_constant_across_the_population() -> None:
    """Invariant from the regression charter: a constant skill is the signature of a
    silent default, and it is invisible in every other test.

    A skill that resolves for *nobody* is the same defect one step further along — a
    skill declared in `SKILL_KEYS` whose source column never reaches the frame. It used
    to raise `IndexError` from indexing an empty list, which is a failure but not a
    legible one, so it is asserted first and by name.
    """
    league = _league_frame()
    vectors = [player_skill_vector(league.iloc[i], league) for i in range(len(league))]
    for key in SKILL_KEYS:
        values = [v[key] for v in vectors if key in v]
        assert values, (
            f"{key} is declared in SKILL_KEYS but resolved for none of the "
            f"{len(vectors)} players — its source column never reaches the frame"
        )
        assert len(set(values)) > 1, f"{key} is constant at {values[0]}"
        assert pd.Series(values).std() > 0.05, f"{key} has near-zero spread"


# -------------------------------------------------------------------- structural

# The literals that produced the audit's findings, each a fabricated stand-in for a
# measurement rather than a constant of the domain:
#
#   0.5   a 50th-percentile player, substituted for an absent skill or an empty side
#   0.75  a default availability for a player with no games-played history
#   12.0  a default minutes estimate for a player the model never scored
#   0.85  the availability of an *empty* incoming list, printed as a measurement
#   1.5   TEI_SIGMA_DEFAULT, giving an unmodelled player a star's confidence band
#
# Constants of the domain (240 team minutes, the 0..100 scale, accumulator zeros) are
# deliberately absent from this set: they are not substitutes for measurements.
FORBIDDEN_LITERALS = {"0.5", "0.75", "12.0", "0.85", "1.5"}


def _fallback_literals(path: Path) -> list[tuple[int, str, str]]:
    """`x.get(k, <literal>)` and `x or <literal>` occurrences, with their line."""
    tree = ast.parse(path.read_text())
    found: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and len(node.args) == 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, int | float)
            and not isinstance(node.args[1].value, bool)
        ):
            found.append((node.lineno, "get-default", repr(float(node.args[1].value))))
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            for value in node.values[1:]:
                if (
                    isinstance(value, ast.Constant)
                    and isinstance(value.value, int | float)
                    and not isinstance(value.value, bool)
                ):
                    found.append((node.lineno, "or-default", repr(float(value.value))))
    return found


@pytest.mark.parametrize("path", SCANNED, ids=lambda p: p.name)
def test_no_league_average_literal_stands_in_for_a_measurement(path: Path) -> None:
    forbidden = {f"{float(x):g}" for x in FORBIDDEN_LITERALS}
    offenders = [
        f"{path.name}:{lineno} {kind} {float(literal):g}"
        for lineno, kind, literal in _fallback_literals(path)
        if f"{float(literal):g}" in forbidden
    ]
    assert not offenders, (
        "a numeric fallback that stands in for a measurement reached a scored path:\n  "
        + "\n  ".join(offenders)
        + "\nIf the value is genuinely a constant of the domain rather than a "
        "substitute for a measurement, document it above FORBIDDEN_LITERALS."
    )


def test_the_scan_would_actually_catch_a_regression(tmp_path: Path) -> None:
    """A guard that can never fire is worse than no guard (see scripts/visual_qa.mjs)."""
    sample = tmp_path / "regression.py"
    sample.write_text("def f(skills):\n    return skills.get('shooting', 0.5)\n")
    literals = {literal for _, _, literal in _fallback_literals(sample)}
    assert "0.5" in {f"{float(x):g}" for x in literals}


def test_impact_is_never_assigned_a_constant() -> None:
    """`tei` must come from a `PlayerImpactEstimate` or be absent — never a literal.

    Parsed rather than grepped, so the historical note in `PlayerCard`'s docstring
    (which quotes the old `tei = 0.0` behaviour) does not trip the check while a real
    assignment would.
    """
    tree = ast.parse((APP / "services" / "evaluation.py").read_text())
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "tei" in targets and isinstance(node.value, ast.Constant):
                offenders.append(f"line {node.lineno}: tei = {node.value.value!r}")
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "tei" and isinstance(kw.value, ast.Constant):
                    offenders.append(f"line {node.lineno}: tei={kw.value.value!r}")
    assert not offenders, "impact was assigned a literal: " + "; ".join(offenders)
