"""Multi-component trade evaluation.

    U = w_P*P + w_F*F + w_C*C + w_T*T + w_A*A + w_R*R      (components on 0..100)

Components with unavailable data (e.g. contract value without a contract provider)
are excluded and the remaining weights renormalized — the composite never contains an
invented number. Every evaluation stores raw calculations, uncertainty, and
sensitivity so the composite is explainable rather than a magic score."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.age_curve import timeline_alignment
from app.analytics.archetypes import (
    SKILL_KEYS,
    UNADDRESSABLE_NEEDS,
    player_skill_vector,
    skill_schema_fingerprint,
)
from app.analytics.components import bounded_score
from app.analytics.features import build_player_season_features, recency_weighted_features
from app.analytics.fit import fit_score
from app.analytics.needs import NEED_TO_SKILL
from app.analytics.projection import (
    ROTATION_DEPTH,
    RotationPlayer,
    allocate_rotation,
    net_rating_delta_to_wins,
    team_tei_to_net_rating_delta,
)
from app.analytics.sensitivity import (
    component_contributions,
    composite_utility,
    normalize_weights,
    tornado,
)
from app.analytics.uncertainty import (
    RotationDraw,
    rotation_draw_from,
    simulate_delta_wins,
)
from app.cba import resolver
from app.cba.builder import build_trade_context, load_cap_params, player_salaries
from app.cba.engine import TradeLegalityEngine
from app.config import get_settings
from app.core.cache import get_cache
from app.db.models import (
    ModelVersion,
    Player,
    PlayerImpactEstimate,
    RosterEntry,
    TeamNeed,
)

DEFAULT_WEIGHTS: dict[str, dict[str, float]] = {
    "contend": {
        "performance": 0.32,
        "fit": 0.20,
        "contract": 0.08,
        "timeline": 0.12,
        "assets": 0.08,
        "risk": 0.20,
    },
    "improve": {
        "performance": 0.25,
        "fit": 0.20,
        "contract": 0.12,
        "timeline": 0.13,
        "assets": 0.15,
        "risk": 0.15,
    },
    "retool": {
        "performance": 0.20,
        "fit": 0.18,
        "contract": 0.14,
        "timeline": 0.18,
        "assets": 0.18,
        "risk": 0.12,
    },
    "rebuild": {
        "performance": 0.08,
        "fit": 0.10,
        "contract": 0.17,
        "timeline": 0.25,
        "assets": 0.28,
        "risk": 0.12,
    },
    "youth": {
        "performance": 0.10,
        "fit": 0.14,
        "contract": 0.14,
        "timeline": 0.28,
        "assets": 0.22,
        "risk": 0.12,
    },
    "cap_relief": {
        "performance": 0.10,
        "fit": 0.10,
        "contract": 0.30,
        "timeline": 0.12,
        "assets": 0.26,
        "risk": 0.12,
    },
    "custom": {
        "performance": 0.22,
        "fit": 0.18,
        "contract": 0.14,
        "timeline": 0.16,
        "assets": 0.15,
        "risk": 0.15,
    },
}

TEI_SIGMA_DEFAULT = 1.5  # index points; refined by per-player bands when available

COMPONENT_KEYS = ("performance", "fit", "contract", "timeline", "assets", "risk")


# How many rotation rows the CHART shows. A display choice, deliberately independent of
# `projection.ROTATION_DEPTH`, which is a basketball claim about who matters.
ROTATION_VIEW_SIZE = 12


def _rotation_view(detail: list[dict], must_include: set[str]) -> list[dict]:
    """The rotation rows the UI charts: the top 12 by minutes, plus everyone in the deal.

    QA-6: `detail[:12]` sliced in **roster order**, not by minutes, so the chart read
    "Josh Giddey 20.4 → 0.0; Jalen Smith 0.0 → 12.4" for a Giddey-for-Curry trade —
    Curry absent, and a fabricated change for a player who was not in the deal, because
    removing one player shifted the index alignment between the two lists.

    Sorting fixes the ordering; `must_include` fixes the omission, because an acquired
    bench player can legitimately fall outside the top 12 and still be the whole point of
    the chart.
    """
    ordered = sorted(detail, key=lambda row: row["minutes"], reverse=True)
    keep = {row["player_id"] for row in ordered[:ROTATION_VIEW_SIZE]} | must_include
    # Re-filtered from `ordered` rather than appended, so an included player outside the
    # top 12 lands at their real position in the chart instead of on the end.
    return [row for row in ordered if row["player_id"] in keep]


def _is_illegal(legality: dict, team_id: str) -> bool:
    """True when the trade fails an implemented rule, for this team or as a whole.

    A trade that is illegal for any participant cannot be executed by anyone, so the
    overall verdict gates every team's score, not just the offending one's."""
    if legality.get("overall_status") == "verified_illegal":
        return True
    return legality.get("teams", {}).get(team_id, {}).get("status") == "verified_illegal"


@dataclass
class PlayerCard:
    """Every modelled quantity is optional.

    A player with no `PlayerImpactEstimate` used to arrive with `tei = 0.0`,
    `availability = 0.75` and `minutes = 12.0`. None of those is a measurement, and
    `tei = 0.0` is the **63rd percentile** of rostered players — a silent default more
    favourable than the −0.293 league mean suggests, and one that directly contradicts
    `docs/model-card-player-impact.md`. Absent values are now absent.
    """

    player_id: str
    name: str
    tei: float | None
    tei_sigma: float | None
    availability: float | None
    minutes: float | None
    age: float | None
    skills: dict[str, float]

    @property
    def is_modeled(self) -> bool:
        return self.tei is not None


class EvaluationService:
    """Builds per-team evaluations for a trade under a scenario."""

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self._impact_cache: dict[str, PlayerImpactEstimate] | None = None
        self._skills_cache: dict[str, dict[str, float]] | None = None
        self._wins_mapping: dict | None = None
        # Per-service memoization. `generate_candidates` builds one service and then
        # evaluates 400 trades against the same handful of rosters, so these were
        # re-queried hundreds of times for identical answers.
        self._roster_cache: dict[str, list[PlayerCard]] = {}
        self._needs_cache: dict[str, dict[str, float]] = {}

    # ------------------------------------------------------------- data loading

    def _impacts(self) -> dict[str, PlayerImpactEstimate]:
        if self._impact_cache is None:
            model = self.db.scalar(
                select(ModelVersion).where(
                    ModelVersion.model_name == "player_impact", ModelVersion.is_active
                )
            )
            rows: list[PlayerImpactEstimate] = []
            if model is not None:
                rows = list(
                    self.db.scalars(
                        select(PlayerImpactEstimate).where(
                            PlayerImpactEstimate.model_version_id == model.id
                        )
                    ).all()
                )
            self._impact_cache = {r.player_id: r for r in rows}
        return self._impact_cache

    def _skills(self) -> dict[str, dict[str, float]]:
        if self._skills_cache is None:
            cache = get_cache()
            # The data-version namespace alone is bumped by ingestion, never by a
            # deploy, so a release that changes the skill contract would keep serving the
            # previous shape for the rest of the six-hour TTL. The fingerprint closes it.
            key = cache.versioned_key("skills", skill_schema_fingerprint())
            cached = cache.get_json(key)
            if cached:
                self._skills_cache = cached
            else:
                season_df = build_player_season_features(self.db)
                weighted = recency_weighted_features(season_df, self.settings.history_season_list)
                skills = {}
                for _, row in weighted.iterrows():
                    skills[row["player_id"]] = player_skill_vector(row, weighted)
                self._skills_cache = skills
                cache.set_json(key, skills, ttl_seconds=6 * 3600)
        return self._skills_cache

    def wins_mapping(self) -> dict:
        if self._wins_mapping is None:
            model = self.db.scalar(
                select(ModelVersion).where(
                    ModelVersion.model_name == "team_projection", ModelVersion.is_active
                )
            )
            self._wins_mapping = (
                model.validation_metrics
                if model
                else {"slope": 2.7, "intercept": 41.0, "calibrated": False}
            )
        return self._wins_mapping

    def _card(self, player: Player, roster_age: float | None = None) -> PlayerCard:
        impact = self._impacts().get(player.id)
        tei: float | None = float(impact.tei) if impact else None
        sigma: float | None = None
        if impact:
            sigma = (
                max((impact.tei_high - impact.tei_low) / 2.5631, 0.4)
                if impact.tei_high is not None and impact.tei_low is not None
                else TEI_SIGMA_DEFAULT
            )
        age: float | None = roster_age
        if age is None and player.birth_date:
            age = (date.today() - player.birth_date).days / 365.25
        return PlayerCard(
            player_id=player.id,
            name=player.full_name,
            tei=tei,
            tei_sigma=sigma,
            availability=(
                float(impact.availability)
                if impact and impact.availability is not None
                else None
            ),
            minutes=(
                float(impact.minutes_estimate)
                if impact and impact.minutes_estimate is not None
                else None
            ),
            age=age,
            skills=self._skills().get(player.id, {}),
        )

    def _roster_cards(self, team_id: str) -> list[PlayerCard]:
        if team_id in self._roster_cache:
            return self._roster_cache[team_id]
        entries = self.db.scalars(
            select(RosterEntry)
            .where(
                RosterEntry.team_id == team_id,
                RosterEntry.season == self.settings.current_season,
                RosterEntry.is_current,
            )
            # Without an explicit order this returned whatever the database happened to
            # produce, so every `[:12]` downstream was an arbitrary 12 rather than a
            # top 12 — and the order changed between runs on Postgres.
            .order_by(RosterEntry.player_id)
        ).all()
        cards = [self._card(e.player, e.age) for e in entries]
        self._roster_cache[team_id] = cards
        return cards

    def _team_needs(self, team_id: str) -> dict[str, float]:
        if team_id not in self._needs_cache:
            rows = self.db.scalars(
                select(TeamNeed).where(
                    TeamNeed.team_id == team_id, TeamNeed.season == self.settings.current_season
                )
            ).all()
            self._needs_cache[team_id] = {r.need_key: r.severity for r in rows}
        return self._needs_cache[team_id]

    # ------------------------------------------------------------- components

    def _performance(
        self, roster: list[PlayerCard], incoming: list[PlayerCard], outgoing_ids: set[str]
    ) -> tuple[float | None, dict]:
        """Players with no impact estimate are excluded from the rotation and named.

        The alternative — giving them `tei = 0.0` and 12 baseline minutes — put a player
        with zero data at the 63rd percentile of the league and let them move the
        projection. Excluding them mirrors the deliberate `min_total_minutes = 200`
        exclusion already in the feature pipeline; the difference is that this one is
        *visible*, and the roster count still includes them.
        """

        def to_rotation(cards: list[PlayerCard]) -> list[RotationPlayer]:
            rotation: list[RotationPlayer] = []
            for c in cards:
                if c.tei is None or c.minutes is None:
                    continue
                rotation.append(
                    RotationPlayer(
                        player_id=c.player_id,
                        name=c.name,
                        tei=c.tei,
                        baseline_minutes=c.minutes,
                        # An unknown availability is not a discount; it is no discount,
                        # and the risk component reports that it could not be measured.
                        availability=1.0 if c.availability is None else c.availability,
                    )
                )
            return rotation

        after_cards = [c for c in roster if c.player_id not in outgoing_ids] + incoming
        unmodeled = sorted(
            {c.name for c in roster + incoming if c.tei is None or c.minutes is None}
        )

        before_rotation = to_rotation(roster)
        after_rotation = to_rotation(after_cards)
        # An EMPTY post-trade rotation is not an unmodellable roster — it is a roster of
        # 240 replacement-level minutes, which is exactly what `allocate_rotation` now
        # models (R3-3). Only a team with nothing to compare against is unprojectable.
        if not before_rotation:
            return None, {
                "unavailable": "no player on this roster has an impact estimate, so the "
                "rotation cannot be projected",
                "unmodeled_players": unmodeled,
            }

        before = allocate_rotation(before_rotation)
        after = allocate_rotation(after_rotation)
        # R3-5: one definition of delta_net. The point estimate and the Monte Carlo must
        # compute the same quantity through the same conversion, or they disagree by the
        # size of the coefficient.
        delta_net = team_tei_to_net_rating_delta(before, after)
        delta_wins = net_rating_delta_to_wins(delta_net, self.wins_mapping())
        # 5 points per projected win — ±10 wins still spans the scale as documented, but
        # through `bounded_score`, so a +15-win deal no longer scores identically to a
        # +10-win one (see analytics/components.py).
        score = bounded_score(50.0 + delta_wins * 5.0)
        return score, {
            "delta_net_rating": round(delta_net, 2),
            "delta_wins": round(delta_wins, 2),
            "rotation_before": _rotation_view(before.detail, outgoing_ids),
            "rotation_after": _rotation_view(
                after.detail, {c.player_id for c in incoming}
            ),
            "wins_mapping": self.wins_mapping(),
            "unmodeled_players": unmodeled,
            "modeled_players_after": len(after_rotation),
            "roster_players_after": len(after_cards),
            # The one allocation both the point estimate and the simulation read (R3-5).
            "_rotations": (before, after),
        }

    def _fit(
        self,
        team_id: str,
        roster: list[PlayerCard],
        incoming: list[PlayerCard],
        outgoing: list[PlayerCard],
    ) -> tuple[float | None, dict]:
        needs = self._team_needs(team_id)
        if not needs:
            return None, {"unavailable": "team needs not computed; run `make score`"}

        # Fit compares the arriving package against the departing one. With nothing on a
        # side there is no package to compare, and the old code substituted a
        # 50th-percentile player for it — so trading everyone away for nothing scored as
        # if a median NBA rotation player had been acquired in every skill. Rather than
        # invent a replacement percentile here, the component is withheld. R5 replaces
        # this with a measured replacement baseline so one-way deals can be scored.
        incoming_entries = [(c.skills, c.minutes) for c in incoming if c.skills and c.minutes]
        outgoing_entries = [(c.skills, c.minutes) for c in outgoing if c.skills and c.minutes]
        if not incoming_entries or not outgoing_entries:
            return None, {
                "unavailable": (
                    "roster fit compares the arriving package with the departing one; "
                    "one side of this deal has no player with a skill profile and "
                    "minutes estimate, so there is nothing to compare"
                ),
                "needs": needs,
            }

        with_minutes = [c for c in roster if c.minutes is not None]
        # ROTATION_DEPTH, not a local 9: the depth at which a roster counts as strong in
        # a skill must match the depth at which `REPLACEMENT_TEI` says a player becomes
        # replaceable (R4-4).
        top_rotation = sorted(with_minutes, key=lambda c: c.minutes or 0.0, reverse=True)[
            :ROTATION_DEPTH
        ]
        roster_strengths: dict[str, float | None] = {}
        for key in SKILL_KEYS:
            values = sorted(
                c.skills[key] for c in top_rotation if c.skills and key in c.skills
            )
            # Third-best is the "already strong here" threshold; with fewer than three
            # observations the roster's strength in that skill is unknown, not average.
            roster_strengths[key] = values[-3] if len(values) >= 3 else None

        score, detail = fit_score(
            needs=needs,
            incoming=incoming_entries,
            outgoing=outgoing_entries,
            roster_strengths=roster_strengths,
            need_to_skill=NEED_TO_SKILL,
        )
        # Attach the reason a measured need has no player-side answer, so the UI can say
        # why rather than silently omitting a weakness the same page reports (R4-2).
        withheld = {
            key: UNADDRESSABLE_NEEDS[key]
            for key in detail.get("needs_without_a_skill", [])
            if key in UNADDRESSABLE_NEEDS
        }
        return bounded_score(50.0 + score * 120.0), {
            **detail,
            "raw_fit": round(score, 4),
            "needs_not_addressable": withheld,
            "needs": needs,
        }

    def _contract_value(
        self,
        incoming: list[PlayerCard],
        outgoing: list[PlayerCard],
        salaries: dict[str, int | None],
        cap: int,
    ) -> tuple[float | None, dict]:
        """Cap-dollar-per-impact heuristic (documented in docs/methodology.md).
        Returns None — excluded from the composite — when any salary is unknown."""
        cards = incoming + outgoing
        if any(salaries.get(c.player_id) is None for c in cards):
            return None, {
                "unavailable": "contract data missing; contract-value component excluded "
                "and weights renormalized"
            }
        unmodeled = sorted({c.name for c in cards if c.tei is None})
        if unmodeled:
            return None, {
                "unavailable": "contract value compares salary against modelled impact, "
                "and these players have no impact estimate: " + ", ".join(unmodeled)
            }

        def market_share(tei: float) -> float:
            # replacement ≈ minimum deal (~2.5% of cap); league-average rotation ≈ 8%;
            # star (+5) ≈ 25%; ceiling 35% (max contract)
            return max(0.025, min(0.35, 0.08 + 0.034 * tei))

        def surplus(cards_: list[PlayerCard]) -> float:
            total = 0.0
            for c in cards_:
                actual = (salaries.get(c.player_id) or 0) / cap
                assert c.tei is not None  # guarded above: unmodelled players withhold this component
                total += market_share(c.tei) - actual
            return total

        net_surplus = surplus(incoming) - surplus(outgoing)  # in cap-share units
        return bounded_score(50.0 + net_surplus * 250.0), {
            "net_surplus_cap_share": round(net_surplus, 4),
            "method": "cap-dollar-per-impact heuristic (no historical salary model data)",
        }

    def _timeline(
        self, strategy: str, incoming: list[PlayerCard], outgoing: list[PlayerCard]
    ) -> tuple[float | None, dict]:
        unweighted_sides: list[str] = []

        def alignment(cards: list[PlayerCard], label: str) -> float | None:
            aged = [c for c in cards if c.age]
            if not aged:
                return None
            # Minutes weight this when it is known. When it is not, the average is
            # unweighted and the response says so — an assumed 12 minutes would be a
            # measurement the pipeline never made.
            if all(c.minutes is None for c in aged):
                unweighted_sides.append(label)
                return sum(timeline_alignment(c.age or 0.0, strategy) for c in aged) / len(aged)
            weighted = [
                (timeline_alignment(c.age or 0.0, strategy), c.minutes)
                for c in aged
                if c.minutes is not None
            ]
            total_weight = sum(w for _, w in weighted)
            if total_weight <= 0:
                unweighted_sides.append(label)
                return sum(timeline_alignment(c.age or 0.0, strategy) for c in aged) / len(aged)
            return sum(a * w for a, w in weighted) / total_weight

        align_in = alignment(incoming, "incoming")
        align_out = alignment(outgoing, "outgoing")
        if align_in is None or align_out is None:
            return None, {"unavailable": "player ages missing"}
        detail: dict[str, Any] = {
            "strategy": strategy,
            "incoming_alignment": round(align_in, 3),
            "outgoing_alignment": round(align_out, 3),
        }
        if unweighted_sides:
            detail["weighting_note"] = (
                "no minutes estimate for "
                + " and ".join(unweighted_sides)
                + "; alignment is an unweighted average"
            )
        return bounded_score(50.0 + (align_in - align_out) * 100.0), detail

    def _assets(
        self,
        picks_in: int,
        picks_out: int,
        payroll_delta: int | None,
        roster_spots_delta: int,
    ) -> tuple[float, dict]:
        score = 50.0 + 8.0 * (picks_in - picks_out) - 2.0 * roster_spots_delta
        detail: dict[str, Any] = {
            "picks_in": picks_in,
            "picks_out": picks_out,
            "roster_spots_delta": roster_spots_delta,
        }
        if payroll_delta is not None:
            score += -payroll_delta / 5_000_000  # $5M added payroll ≈ -1 point flexibility
            detail["payroll_delta"] = payroll_delta
        else:
            detail["payroll_note"] = "payroll delta unknown (no contract data)"
        return bounded_score(score), detail

    def _risk(
        self, incoming: list[PlayerCard], outgoing: list[PlayerCard], uncertainty: dict
    ) -> tuple[float | None, dict]:
        """Two terms, each contributed only when it can actually be measured.

        Previously both had silent fallbacks: `prob_positive` defaulted to 0.5 and, worse,
        the availability of an *empty* incoming list was reported as 0.85 — a number the
        executive report printed as a measurement (QA-8). Terms that cannot be computed
        are dropped and the survivors renormalized, the same contract the composite uses.
        """
        terms: list[tuple[float, float]] = []  # (value 0..1, weight)
        detail: dict[str, Any] = {}

        prob_positive = uncertainty.get("prob_positive")
        if prob_positive is not None:
            terms.append((float(prob_positive), 60.0))
            detail["prob_positive_outcome"] = prob_positive
        else:
            detail["prob_positive_outcome"] = None

        known_availability = [c.availability for c in incoming if c.availability is not None]
        if known_availability:
            avail_in = sum(known_availability) / len(known_availability)
            terms.append((avail_in, 40.0))
            detail["incoming_availability"] = round(avail_in, 3)
            detail["incoming_availability_players"] = len(known_availability)
        else:
            detail["incoming_availability"] = None

        if not terms:
            detail["unavailable"] = (
                "no incoming players and no outcome distribution — downside risk cannot "
                "be scored for this deal"
            )
            return None, detail

        total_weight = sum(w for _, w in terms)
        score = sum(value * weight for value, weight in terms) / total_weight * 100.0
        return max(0.0, min(100.0, score)), detail

    # ------------------------------------------------------------- suppression

    def _suppressed_for_illegality(
        self,
        team_id: str,
        team_legality: dict,
        legality: dict,
        weights: dict[str, float],
        incoming: list[PlayerCard],
        outgoing: list[PlayerCard],
    ) -> dict:
        """The response shape is unchanged; every score-bearing field is null.

        Keeping the keys means no consumer has to branch on their absence, and
        `decision_status` distinguishes "we refuse to score this" from "we could not
        score this" — two different `composite_utility: null` cases that the old contract
        could not tell apart."""
        failing = [
            {
                "rule_code": r["rule_code"],
                "team_id": r["team_id"],
                "message": r["message"],
                "calculation": r.get("calculation", {}),
                "source_reference": r.get("source_reference", ""),
            }
            for r in legality.get("rule_results", [])
            if r.get("status") == "fail"
        ]
        unmodeled_players = sorted({c.name for c in incoming + outgoing if c.tei is None})
        return {
            "team_id": team_id,
            "legality": team_legality,
            "has_unmodeled_players": bool(unmodeled_players),
            "unmodeled_players": unmodeled_players,
            "decision_status": "suppressed_illegal",
            "suppression": {
                "reason": "verified_illegal",
                "message": "This trade fails at least one implemented CBA rule, so it "
                "cannot be executed as constructed. No decision score is reported for a "
                "deal that cannot happen.",
                "failing_rules": failing,
            },
            "composite_utility": None,
            "confidence": "not_applicable",
            "components": dict.fromkeys(COMPONENT_KEYS),
            "excluded_components": list(COMPONENT_KEYS),
            "drivers": [],
            "weights": weights,
            "detail": {},
            "uncertainty": {},
            "sensitivity_tornado": [],
            "incoming": [self._player_summary(c) for c in incoming],
            "outgoing": [self._player_summary(c) for c in outgoing],
            "evaluated_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _player_summary(card: PlayerCard) -> dict:
        return {
            "player_id": card.player_id,
            "name": card.name,
            "tei": round(card.tei, 2) if card.tei is not None else None,
        }

    # ------------------------------------------------------------- entry point

    def evaluate_for_team(
        self,
        team_id: str,
        team_ids: list[str],
        player_moves: list[dict],
        pick_moves: list[dict],
        strategy: str = "custom",
        weights: dict[str, float] | None = None,
        legality: dict | None = None,
    ) -> dict:
        weights = normalize_weights(
            weights or DEFAULT_WEIGHTS.get(strategy, DEFAULT_WEIGHTS["custom"])
        )
        roster = self._roster_cards(team_id)
        incoming_ids = [m["player_id"] for m in player_moves if m["to_team_id"] == team_id]
        outgoing_ids = [m["player_id"] for m in player_moves if m["from_team_id"] == team_id]
        # Batched and session-cached: this was one `SELECT … FROM players WHERE id IN …`
        # per team per evaluation, i.e. 800 of the 815 queries a `/trades/generate`
        # request still issued after the salary batching.
        incoming = [
            self._card(player)
            for player in resolver.players(self.db, incoming_ids).values()
        ]
        outgoing = [c for c in roster if c.player_id in set(outgoing_ids)]

        if legality is None:
            context = build_trade_context(self.db, team_ids, player_moves, pick_moves)
            legality = TradeLegalityEngine().evaluate(context)
        team_legality = legality["teams"].get(team_id, {})

        # A trade that fails an implemented CBA rule cannot be executed, so there is no
        # decision to score. The failing rules and their dollar figures are still
        # returned — the refusal is explained, not silent.
        if _is_illegal(legality, team_id):
            return self._suppressed_for_illegality(
                team_id, team_legality, legality, weights, incoming, outgoing
            )

        # One batched lookup, and the imports are module-level: these two were
        # function-local imports of a private helper inside the hot path, executed about
        # 800 times per `/trades/generate` request.
        resolved = player_salaries(
            self.db, [c.player_id for c in incoming + outgoing], self.settings.cap_league_year
        )
        salaries: dict[str, int | None] = {pid: value[0] for pid, value in resolved.items()}

        cap_params = load_cap_params(self.db, self.settings.cap_league_year)
        performance, perf_detail = self._performance(roster, incoming, set(outgoing_ids))
        fit_value, fit_detail = self._fit(team_id, roster, incoming, outgoing)
        contract, contract_detail = self._contract_value(
            incoming, outgoing, salaries, cap_params.salary_cap
        )
        timeline, timeline_detail = self._timeline(strategy, incoming, outgoing)

        picks_in = len([m for m in pick_moves if m["to_team_id"] == team_id])
        picks_out = len([m for m in pick_moves if m["from_team_id"] == team_id])
        payroll_before = team_legality.get("payroll_before")
        payroll_after = team_legality.get("payroll_after")
        payroll_delta = (
            payroll_after - payroll_before
            if payroll_after is not None and payroll_before is not None
            else None
        )
        assets, assets_detail = self._assets(
            picks_in, picks_out, payroll_delta, len(incoming) - len(outgoing)
        )

        # R3-5: the simulation draws over the SAME rotation the point estimate allocated.
        # An unmodelled player used to receive TEI_SIGMA_DEFAULT = 1.5, expressing the
        # same confidence about a player with no data as about a 36-minute star; they are
        # excluded from the rotation entirely and named in the response instead.
        sigma_by_player = {
            c.player_id: c.tei_sigma
            for c in roster + incoming + outgoing
            if c.tei_sigma is not None
        }
        rotations = perf_detail.pop("_rotations", None)
        if rotations is None:
            uncertainty = simulate_delta_wins(
                RotationDraw(), RotationDraw(), wins_mapping=self.wins_mapping()
            )
        else:
            before_rot, after_rot = rotations
            uncertainty = simulate_delta_wins(
                before=rotation_draw_from(before_rot.detail, sigma_by_player),
                after=rotation_draw_from(after_rot.detail, sigma_by_player),
                wins_mapping=self.wins_mapping(),
                moved_keys={c.player_id for c in incoming + outgoing},
            )
        unmodeled_in_deal = sorted({c.name for c in incoming + outgoing if c.tei is None})
        if unmodeled_in_deal:
            uncertainty["unmodeled_players_excluded"] = unmodeled_in_deal
        risk, risk_detail = self._risk(incoming, outgoing, uncertainty)

        components = {
            "performance": performance,
            "fit": fit_value,
            "contract": contract,
            "timeline": timeline,
            "assets": assets,
            "risk": risk,
        }
        utility = composite_utility(components, weights)
        excluded = [k for k, v in components.items() if v is None]
        drivers = component_contributions(components, weights)

        # Players on this side of the deal, or on the roster it is evaluated against,
        # that the impact model has never scored.
        unmodeled_players = sorted(
            {c.name for c in roster + incoming + outgoing if c.tei is None}
        )

        confidence = "high"
        if excluded:
            confidence = "medium" if len(excluded) <= 2 else "low"
        if unmodeled_in_deal:
            # A player in the deal itself with no impact estimate is a bigger hole than
            # one sitting at the end of the bench.
            confidence = "low"
        elif unmodeled_players and confidence == "high":
            confidence = "medium"

        return {
            "team_id": team_id,
            "legality": team_legality,
            "has_unmodeled_players": bool(unmodeled_players),
            "unmodeled_players": unmodeled_players,
            "decision_status": "scored" if utility is not None else "insufficient_data",
            "suppression": None
            if utility is not None
            else {
                "reason": "insufficient_data",
                "message": "No component could be scored for this team, so no decision "
                "score is reported.",
            },
            "composite_utility": round(utility, 2) if utility is not None else None,
            "confidence": confidence,
            "components": {
                k: (round(v, 2) if v is not None else None) for k, v in components.items()
            },
            "excluded_components": excluded,
            "drivers": drivers,
            "weights": weights,
            "detail": {
                "performance": perf_detail,
                "fit": fit_detail,
                "contract": contract_detail,
                "timeline": timeline_detail,
                "assets": assets_detail,
                "risk": risk_detail,
            },
            "uncertainty": uncertainty,
            "sensitivity_tornado": tornado(components, weights),
            "incoming": [self._player_summary(c) for c in incoming],
            "outgoing": [self._player_summary(c) for c in outgoing],
            "evaluated_at": datetime.now(UTC).isoformat(),
        }
