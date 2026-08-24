"""Do the acquisition targets change because the basketball changes?

A need-driven target list is easy to fake. Filter on anything and rank by talent, and every
team is handed the same five superstars with a different sentence attached. The measurement
that matters is whether the list moves with the team's actual situation, and whether it
moves for the stated reason rather than for the team's name.

Everything here runs against the ingested league. `make acquisition-validation` prints the
whole battery and exits non-zero when a stated threshold fails.

## Team types

Classified from measured quantities, never from a label:

- **direction** — win percentage tertile among the 30 ingested teams: `contender`,
  `middle`, `rebuilding`. A team's own record, not an opinion about its plans.
- **concentration** — the share of the roster's total above-replacement value held by its
  top two players. Upper tertile is `star_heavy`, lower is `balanced`.
- **weakness** — the skill family of the team's most severe addressable need:
  `shooting`, `creation`, `size`, `defence`, `other`.

## The nulls

- **no filter** — rank every league player by projected wins and take the top five. This is
  what a target list looks like when the need does nothing.
- **need shuffled** — give each team the need of the team after it in alphabetical order,
  and re-run. If the lists barely move, the need is decoration.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.projection import REPLACEMENT_TEI, TEAM_MINUTES
from app.config import get_settings
from app.db.models import Standing, Team
from app.services.acquisition import acquisition_targets
from app.services.evaluation import EvaluationService

TOP_K = 5

THRESHOLDS: dict[str, float] = {
    #: The filtered list must name more distinct players across the league than the
    #: unfiltered one. Below this the need is not doing any work.
    "distinct_target_ratio_min": 1.5,
    #: Two teams with the same diagnosed need must be told something more alike than two
    #: teams with different needs. If they are not, the need is not what drives the list.
    "same_need_overlap_lift_min": 0.05,
    #: ...and not identical either, or the list is a lookup table on the need.
    "same_need_overlap_max": 0.9,
    #: Every returned target must improve the need it was returned for. This is a property,
    #: not a tendency.
    "improves_the_need_share_min": 1.0,
}


@dataclass
class TeamProfile:
    abbreviation: str
    team_id: str
    win_pct: float | None
    direction: str
    concentration: float | None
    concentration_class: str
    need_key: str | None
    weakness: str
    targets: list[str] = field(default_factory=list)
    unfiltered_targets: list[str] = field(default_factory=list)
    available: bool = True
    unavailable_reason: str | None = None
    feasibility: dict = field(default_factory=dict)


WEAKNESS_FAMILY = {
    "three_point_volume": "shooting",
    "shooting_efficiency": "shooting",
    "offense_overall": "shooting",
    "playmaking": "creation",
    "secondary_creation": "creation",
    "ball_security": "creation",
    "defensive_rebounding": "size",
    "rim_protection": "size",
    "lineup_size": "size",
    "defense_overall": "defence",
    "point_of_attack_defense": "defence",
}


def _jaccard(a: list[str], b: list[str]) -> float:
    left, right = set(a), set(b)
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _tertile_class(value: float | None, cuts: tuple[float, float], names: tuple[str, str, str]) -> str:
    if value is None:
        return "unknown"
    if value <= cuts[0]:
        return names[0]
    if value >= cuts[1]:
        return names[2]
    return names[1]


def _concentration(service: EvaluationService, team_id: str) -> float | None:
    """Share of a roster's above-replacement value held by its two best players."""
    values = sorted(
        (
            (card.minutes / TEAM_MINUTES) * (card.tei - REPLACEMENT_TEI)
            for card in service._roster_cards(team_id)
            if card.tei is not None and card.minutes is not None
        ),
        reverse=True,
    )
    positive = [v for v in values if v > 0]
    total = sum(positive)
    if total <= 0 or len(positive) < 3:
        return None
    return sum(positive[:2]) / total


def run_battery(db: Session, k: int = TOP_K) -> dict[str, Any]:
    settings = get_settings()
    service = EvaluationService(db)
    teams = sorted(db.scalars(select(Team)).all(), key=lambda t: t.abbreviation)
    win_pct = {
        row.team_id: float(row.win_pct)
        for row in db.scalars(
            select(Standing).where(Standing.season == settings.current_season)
        ).all()
    }
    concentrations = {t.id: _concentration(service, t.id) for t in teams}

    known_wins = sorted(v for v in win_pct.values())
    known_conc = sorted(v for v in concentrations.values() if v is not None)
    win_cuts = (
        (known_wins[len(known_wins) // 3], known_wins[2 * len(known_wins) // 3])
        if len(known_wins) >= 3
        else (0.0, 1.0)
    )
    conc_cuts = (
        (known_conc[len(known_conc) // 3], known_conc[2 * len(known_conc) // 3])
        if len(known_conc) >= 3
        else (0.0, 1.0)
    )

    profiles: list[TeamProfile] = []
    for team in teams:
        result = acquisition_targets(db, team.id, limit=k)
        unfiltered = acquisition_targets(db, team.id, limit=k, feasible_only=False)
        need = (result.get("target_need") or {}).get("need_key")
        profiles.append(
            TeamProfile(
                abbreviation=team.abbreviation,
                team_id=team.id,
                win_pct=win_pct.get(team.id),
                direction=_tertile_class(
                    win_pct.get(team.id), win_cuts, ("rebuilding", "middle", "contender")
                ),
                concentration=concentrations.get(team.id),
                concentration_class=_tertile_class(
                    concentrations.get(team.id), conc_cuts, ("balanced", "middle", "star_heavy")
                ),
                need_key=need,
                weakness=WEAKNESS_FAMILY.get(need or "", "other"),
                targets=[t["name"] for t in result.get("targets", [])],
                unfiltered_targets=[t["name"] for t in unfiltered.get("targets", [])],
                available=result.get("available", False),
                unavailable_reason=result.get("unavailable_reason"),
                feasibility=result.get("feasibility", {}),
            )
        )

    answered = [p for p in profiles if p.available and p.targets]
    distinct_filtered = {name for p in answered for name in p.targets}
    distinct_unfiltered = {name for p in answered for name in p.unfiltered_targets}
    ratio = (
        len(distinct_filtered) / len(distinct_unfiltered) if distinct_unfiltered else 0.0
    )

    same_need: list[float] = []
    cross_need: list[float] = []
    for i, left in enumerate(answered):
        for right in answered[i + 1 :]:
            overlap = _jaccard(left.targets, right.targets)
            (same_need if left.need_key == right.need_key else cross_need).append(overlap)
    same_mean = statistics.fmean(same_need) if same_need else 0.0
    cross_mean = statistics.fmean(cross_need) if cross_need else 0.0

    # Shuffled-need null: each team gets the next team's diagnosed need.
    shuffled_overlaps = []
    for index, profile in enumerate(answered):
        donor = answered[(index + 1) % len(answered)]
        if donor.need_key is None or donor.need_key == profile.need_key:
            continue
        try:
            alternative = acquisition_targets(
                db, profile.team_id, need_key=donor.need_key, limit=k
            )
        except Exception:
            continue
        if alternative.get("available"):
            shuffled_overlaps.append(
                _jaccard(profile.targets, [t["name"] for t in alternative.get("targets", [])])
            )

    improves = [
        target
        for profile in answered
        for target in [acquisition_targets(db, profile.team_id, limit=k)]
    ]
    improving = sum(
        1
        for result in improves
        for target in result.get("targets", [])
        if target["need_improvement"] > 0
    )
    total_targets = sum(len(result.get("targets", [])) for result in improves)
    improve_share = improving / total_targets if total_targets else 0.0

    on_own_roster = sum(
        1
        for profile in answered
        for result in [acquisition_targets(db, profile.team_id, limit=k)]
        for target in result.get("targets", [])
        if target["team"]["id"] == profile.team_id
    )

    checks: list[dict[str, Any]] = [
        {
            "name": "need_filter_differentiates",
            "measured": round(ratio, 4),
            "threshold": THRESHOLDS["distinct_target_ratio_min"],
            "passed": ratio >= THRESHOLDS["distinct_target_ratio_min"],
            "detail": {
                "distinct_players_filtered": len(distinct_filtered),
                "distinct_players_unfiltered": len(distinct_unfiltered),
                "teams_answered": len(answered),
            },
        },
        {
            "name": "same_need_teams_hear_more_alike",
            "measured": round(same_mean - cross_mean, 4),
            "threshold": THRESHOLDS["same_need_overlap_lift_min"],
            "passed": (same_mean - cross_mean) >= THRESHOLDS["same_need_overlap_lift_min"],
            "detail": {
                "same_need_mean_overlap": round(same_mean, 4),
                "cross_need_mean_overlap": round(cross_mean, 4),
                "same_need_pairs": len(same_need),
                "cross_need_pairs": len(cross_need),
            },
        },
        {
            "name": "context_still_separates_teams_with_one_need",
            "measured": round(same_mean, 4),
            "threshold": THRESHOLDS["same_need_overlap_max"],
            "passed": same_mean <= THRESHOLDS["same_need_overlap_max"],
            "detail": {
                "note": (
                    "Two teams diagnosed with the same need must not be handed the same "
                    "list: their rosters, records and cap positions differ, and the "
                    "targets should too."
                )
            },
        },
        {
            "name": "every_target_improves_its_need",
            "measured": round(improve_share, 4),
            "threshold": THRESHOLDS["improves_the_need_share_min"],
            "passed": improve_share >= THRESHOLDS["improves_the_need_share_min"],
            "detail": {"targets_checked": total_targets, "on_acquiring_roster": on_own_roster},
        },
        {
            "name": "shuffled_need_null",
            "measured": (
                round(statistics.fmean(shuffled_overlaps), 4) if shuffled_overlaps else None
            ),
            "threshold": None,
            "passed": None,
            "detail": {
                "pairs": len(shuffled_overlaps),
                "note": (
                    "Each team re-run with another team's diagnosed need. The overlap with "
                    "its own list is how much the need actually decides."
                ),
            },
        },
    ]

    by_type: dict[str, dict[str, Any]] = {}
    for key in ("direction", "concentration_class", "weakness"):
        groups: dict[str, list[TeamProfile]] = {}
        for profile in answered:
            groups.setdefault(getattr(profile, key), []).append(profile)
        by_type[key] = {
            name: {
                "teams": [p.abbreviation for p in group],
                "distinct_targets": len({t for p in group for t in p.targets}),
                "most_common": _most_common([t for p in group for t in p.targets], 5),
            }
            for name, group in sorted(groups.items())
        }

    return {
        "teams": len(profiles),
        "teams_answered": len(answered),
        "k": k,
        "checks": checks,
        "by_team_type": by_type,
        "unavailable": [
            {"team": p.abbreviation, "reason": p.unavailable_reason}
            for p in profiles
            if not p.available
        ],
        "per_team": [
            {
                "team": p.abbreviation,
                "win_pct": p.win_pct,
                "direction": p.direction,
                "concentration": round(p.concentration, 3) if p.concentration else None,
                "concentration_class": p.concentration_class,
                "need": p.need_key,
                "weakness": p.weakness,
                "targets": p.targets,
                "unfiltered_targets": p.unfiltered_targets,
                "trades_evaluated": p.feasibility.get("trades_evaluated"),
                "rejected": p.feasibility.get("rejected"),
            }
            for p in profiles
        ],
        "failed": [c["name"] for c in checks if c["passed"] is False],
    }


def _most_common(names: list[str], limit: int) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for name in names:
        counts[name] = counts.get(name, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
