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
from app.analytics.archetypes import player_skill_vector
from app.analytics.features import build_player_season_features, recency_weighted_features
from app.analytics.fit import fit_score
from app.analytics.needs import NEED_TO_SKILL
from app.analytics.projection import (
    RotationPlayer,
    allocate_rotation,
    net_rating_delta_to_wins,
)
from app.analytics.sensitivity import composite_utility, normalize_weights, tornado
from app.analytics.uncertainty import PlayerDraw, simulate_delta_wins
from app.cba.builder import build_trade_context
from app.cba.engine import TradeLegalityEngine
from app.config import get_settings
from app.core.cache import get_cache
from app.db.models import (
    ModelVersion,
    Player,
    PlayerImpactEstimate,
    RosterEntry,
    Team,
    TeamNeed,
)

DEFAULT_WEIGHTS: dict[str, dict[str, float]] = {
    "contend": {"performance": 0.32, "fit": 0.20, "contract": 0.08, "timeline": 0.12, "assets": 0.08, "risk": 0.20},
    "improve": {"performance": 0.25, "fit": 0.20, "contract": 0.12, "timeline": 0.13, "assets": 0.15, "risk": 0.15},
    "retool": {"performance": 0.20, "fit": 0.18, "contract": 0.14, "timeline": 0.18, "assets": 0.18, "risk": 0.12},
    "rebuild": {"performance": 0.08, "fit": 0.10, "contract": 0.17, "timeline": 0.25, "assets": 0.28, "risk": 0.12},
    "youth": {"performance": 0.10, "fit": 0.14, "contract": 0.14, "timeline": 0.28, "assets": 0.22, "risk": 0.12},
    "cap_relief": {"performance": 0.10, "fit": 0.10, "contract": 0.30, "timeline": 0.12, "assets": 0.26, "risk": 0.12},
    "custom": {"performance": 0.22, "fit": 0.18, "contract": 0.14, "timeline": 0.16, "assets": 0.15, "risk": 0.15},
}

TEI_SIGMA_DEFAULT = 1.5  # index points; refined by per-player bands when available


@dataclass
class PlayerCard:
    player_id: str
    name: str
    tei: float
    tei_sigma: float
    availability: float
    minutes: float
    age: float | None
    skills: dict[str, float]


class EvaluationService:
    """Builds per-team evaluations for a trade under a scenario."""

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self._impact_cache: dict[str, PlayerImpactEstimate] | None = None
        self._skills_cache: dict[str, dict[str, float]] | None = None
        self._wins_mapping: dict | None = None

    # ------------------------------------------------------------- data loading

    def _impacts(self) -> dict[str, PlayerImpactEstimate]:
        if self._impact_cache is None:
            model = self.db.scalar(
                select(ModelVersion).where(
                    ModelVersion.model_name == "player_impact", ModelVersion.is_active
                )
            )
            rows = (
                self.db.scalars(
                    select(PlayerImpactEstimate).where(
                        PlayerImpactEstimate.model_version_id == (model.id if model else "")
                    )
                ).all()
                if model
                else []
            )
            self._impact_cache = {r.player_id: r for r in rows}
        return self._impact_cache

    def _skills(self) -> dict[str, dict[str, float]]:
        if self._skills_cache is None:
            cache = get_cache()
            key = cache.versioned_key("skills")
            cached = cache.get_json(key)
            if cached:
                self._skills_cache = cached
            else:
                season_df = build_player_season_features(self.db)
                weighted = recency_weighted_features(
                    season_df, self.settings.history_season_list
                )
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
        tei = float(impact.tei) if impact else 0.0
        sigma = TEI_SIGMA_DEFAULT
        if impact and impact.tei_high is not None and impact.tei_low is not None:
            sigma = max((impact.tei_high - impact.tei_low) / 2.5631, 0.4)
        age: float | None = roster_age
        if age is None and player.birth_date:
            age = (date.today() - player.birth_date).days / 365.25
        return PlayerCard(
            player_id=player.id,
            name=player.full_name,
            tei=tei,
            tei_sigma=sigma,
            availability=float(impact.availability) if impact and impact.availability else 0.75,
            minutes=float(impact.minutes_estimate) if impact and impact.minutes_estimate else 12.0,
            age=age,
            skills=self._skills().get(player.id, {}),
        )

    def _roster_cards(self, team_id: str) -> list[PlayerCard]:
        entries = self.db.scalars(
            select(RosterEntry).where(
                RosterEntry.team_id == team_id,
                RosterEntry.season == self.settings.current_season,
                RosterEntry.is_current,
            )
        ).all()
        return [self._card(e.player, e.age) for e in entries]

    def _team_needs(self, team_id: str) -> dict[str, float]:
        rows = self.db.scalars(
            select(TeamNeed).where(
                TeamNeed.team_id == team_id, TeamNeed.season == self.settings.current_season
            )
        ).all()
        return {r.need_key: r.severity for r in rows}

    # ------------------------------------------------------------- components

    def _performance(
        self, roster: list[PlayerCard], incoming: list[PlayerCard], outgoing_ids: set[str]
    ) -> tuple[float | None, dict]:
        def to_rotation(cards: list[PlayerCard]) -> list[RotationPlayer]:
            return [
                RotationPlayer(
                    player_id=c.player_id,
                    name=c.name,
                    tei=c.tei,
                    baseline_minutes=c.minutes,
                    availability=c.availability,
                )
                for c in cards
            ]

        before = allocate_rotation(to_rotation(roster))
        after_cards = [c for c in roster if c.player_id not in outgoing_ids] + incoming
        after = allocate_rotation(to_rotation(after_cards))
        delta_net = after.team_tei_per_minute - before.team_tei_per_minute
        delta_wins = net_rating_delta_to_wins(delta_net, self.wins_mapping())
        # ±10 projected wins spans the full 0..100 scale (documented normalization)
        score = max(0.0, min(100.0, 50.0 + delta_wins * 5.0))
        return score, {
            "delta_net_rating": round(delta_net, 2),
            "delta_wins": round(delta_wins, 2),
            "rotation_before": before.detail[:12],
            "rotation_after": after.detail[:12],
            "wins_mapping": self.wins_mapping(),
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
        top_rotation = sorted(roster, key=lambda c: c.minutes, reverse=True)[:9]
        roster_strengths: dict[str, float] = {}
        for key in ("shooting", "creation", "perimeter_defense", "rim_protection", "rebounding", "size", "scoring"):
            values = [c.skills.get(key, 0.5) for c in top_rotation if c.skills]
            roster_strengths[key] = sorted(values)[-3] if len(values) >= 3 else 0.5
        score, detail = fit_score(
            needs=needs,
            incoming=[(c.skills, c.minutes) for c in incoming if c.skills],
            outgoing=[(c.skills, c.minutes) for c in outgoing if c.skills],
            roster_strengths=roster_strengths,
            need_to_skill=NEED_TO_SKILL,
        )
        return max(0.0, min(100.0, 50.0 + score * 120.0)), {**detail, "needs": needs}

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

        def market_share(tei: float) -> float:
            # replacement ≈ minimum deal (~2.5% of cap); league-average rotation ≈ 8%;
            # star (+5) ≈ 25%; ceiling 35% (max contract)
            return max(0.025, min(0.35, 0.08 + 0.034 * tei))

        def surplus(cards_: list[PlayerCard]) -> float:
            total = 0.0
            for c in cards_:
                actual = (salaries.get(c.player_id) or 0) / cap
                total += market_share(c.tei) - actual
            return total

        net_surplus = surplus(incoming) - surplus(outgoing)  # in cap-share units
        return max(0.0, min(100.0, 50.0 + net_surplus * 250.0)), {
            "net_surplus_cap_share": round(net_surplus, 4),
            "method": "cap-dollar-per-impact heuristic (no historical salary model data)",
        }

    def _timeline(
        self, strategy: str, incoming: list[PlayerCard], outgoing: list[PlayerCard]
    ) -> tuple[float | None, dict]:
        def alignment(cards: list[PlayerCard]) -> float | None:
            weighted = [(timeline_alignment(c.age, strategy), c.minutes) for c in cards if c.age]
            if not weighted:
                return None
            total_weight = sum(w for _, w in weighted)
            return sum(a * w for a, w in weighted) / total_weight

        align_in, align_out = alignment(incoming), alignment(outgoing)
        if align_in is None or align_out is None:
            return None, {"unavailable": "player ages missing"}
        return max(0.0, min(100.0, 50.0 + (align_in - align_out) * 100.0)), {
            "strategy": strategy,
            "incoming_alignment": round(align_in, 3),
            "outgoing_alignment": round(align_out, 3),
        }

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
        return max(0.0, min(100.0, score)), detail

    def _risk(
        self, incoming: list[PlayerCard], outgoing: list[PlayerCard], uncertainty: dict
    ) -> tuple[float, dict]:
        avail_in = (
            sum(c.availability for c in incoming) / len(incoming) if incoming else 0.85
        )
        prob_positive = uncertainty.get("prob_positive", 0.5)
        score = max(0.0, min(100.0, 60.0 * prob_positive + 40.0 * avail_in))
        return score, {
            "prob_positive_outcome": prob_positive,
            "incoming_availability": round(avail_in, 3),
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
        weights = normalize_weights(weights or DEFAULT_WEIGHTS.get(strategy, DEFAULT_WEIGHTS["custom"]))
        roster = self._roster_cards(team_id)
        incoming_ids = [m["player_id"] for m in player_moves if m["to_team_id"] == team_id]
        outgoing_ids = [m["player_id"] for m in player_moves if m["from_team_id"] == team_id]
        incoming = [self._card(p) for p in self.db.scalars(select(Player).where(Player.id.in_(incoming_ids))).all()] if incoming_ids else []
        outgoing = [c for c in roster if c.player_id in set(outgoing_ids)]

        if legality is None:
            context = build_trade_context(self.db, team_ids, player_moves, pick_moves)
            legality = TradeLegalityEngine().evaluate(context)
        team_legality = legality["teams"].get(team_id, {})

        salaries: dict[str, int | None] = {}
        from app.cba.builder import _player_salary

        for card in incoming + outgoing:
            salaries[card.player_id], _ = _player_salary(
                self.db, card.player_id, self.settings.cap_league_year
            )

        from app.cba.builder import load_cap_params

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

        total_minutes = 240.0
        uncertainty = simulate_delta_wins(
            incoming=[
                PlayerDraw(c.tei, c.tei_sigma, c.availability, c.minutes / total_minutes)
                for c in incoming
            ],
            outgoing=[
                PlayerDraw(c.tei, c.tei_sigma, c.availability, c.minutes / total_minutes)
                for c in outgoing
            ],
            wins_mapping=self.wins_mapping(),
        )
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

        drivers = sorted(
            (
                {"component": k, "score": round(v, 1), "weight": weights.get(k, 0),
                 "contribution": round((v - 50.0) * weights.get(k, 0), 2)}
                for k, v in components.items()
                if v is not None
            ),
            key=lambda d: abs(d["contribution"]),
            reverse=True,
        )

        confidence = "high"
        if excluded:
            confidence = "medium" if len(excluded) <= 2 else "low"

        return {
            "team_id": team_id,
            "legality": team_legality,
            "composite_utility": round(utility, 2),
            "confidence": confidence,
            "components": {k: (round(v, 2) if v is not None else None) for k, v in components.items()},
            "excluded_components": excluded,
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
            "incoming": [{"player_id": c.player_id, "name": c.name, "tei": round(c.tei, 2)} for c in incoming],
            "outgoing": [{"player_id": c.player_id, "name": c.name, "tei": round(c.tei, 2)} for c in outgoing],
            "evaluated_at": datetime.now(UTC).isoformat(),
        }
