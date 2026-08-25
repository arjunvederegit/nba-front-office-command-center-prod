"""Building trade sides from this database, and serving comparable-trade retrieval.

The analytics module owns the distance; this module owns the join. It exists to guarantee
one thing above all: **the query side and every corpus side are built by the same
function.** A retrieval engine whose two halves are constructed differently measures the
construction, not the trades — so `_side` is the only place a `TradeSide` is made, and the
only difference between a proposal and a completed trade is where the legs come from.

## The season a trade is described by

**The most recent body of production a front office actually had.** Until R7 that was
decided from the calendar month — July, August and September were offseason, everything
else in-season — and the month is not enough to decide it. Three groups of trades were
being described by production that did not exist when they were made:

| what the month rule said | what had actually been played |
| --- | --- |
| 33 trades in **November 2020** are 2020-21 | the 2020-21 season began **22 December 2020** |
| 12 trades on **26-28 June 2024** are 2024-25 | Basketball-Reference files draft night under the season about to start; 2023-24 is the season that finished |
| 10 trades in **early October** are that season | first games fall 22-25 October |

The June-2024 group is inside the shipped three-season window, so this was live, not
latent.

R7 replaces the month with the season boundary as **data**. `season_calendar` holds the
first and last regular-season game of each season, ingested from `LeagueGameLog`, and the
rule reads it:

- a trade between a season's first and last game is described by **that** season, and is
  in-season;
- otherwise it is described by the **most recently completed** season, and is not.

Every trade's feature season is named on every result. With no calendar ingested the rule
falls back to the month, reports `calendar_backed: false`, and says so in the response.

## What limits the corpus

A trade whose feature season has no ingested player production has no on-court value to
state, so it is stored, retrievable and counted, but **not ranked**. R6 measured this at
three seasons of `player_season_stats`; R7 widened the corpus window to ten
(`CORPUS_SEASONS`, separate from the modelling window) and re-measured:

    trades ingested                            565      565
    sides in the corpus                      1,225    1,225
    seasons of player production                 3       10
    ...sides with production for their season  352    1,188
    ...rankable                                337    1,136
    ...blocked by an unmodelled player          15       52
    distinct trades rankable                   154      530

The blocked sides each contain a player who had played in the NBA before the trade but
recorded no minutes in its feature season. He is not treated as worthless — the side is
withheld, because pricing him at zero would understate the package by an unknown amount.

A player who had recorded **no** NBA season before the trade — a draft right, a rookie
moved on draft night — contributes zero, and that is a measurement rather than an
imputation.

**Widening the window also corrected sides that were already being ranked.** "No prior NBA
season" is decided against the seasons this database holds, so at three seasons a veteran
whose last season was 2022-23 looked like a player who had never played. 2023-24 loses 8
such legs and 4 sides move from silently priced at zero to honestly withheld. The count
going *down* is the improvement.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.comparables import (
    DIMENSION_LABELS,
    DIMENSION_WEIGHTS,
    FEATURE_DIMENSIONS,
    Neighbour,
    PickLeg,
    PlayerLeg,
    TradeSide,
    compare,
    explain,
    rank,
    robust_scales,
)
from app.analytics.features import build_player_season_features
from app.analytics.impact import add_zscores, baseline_index
from app.config import get_settings
from app.core.errors import NotFoundError
from app.db.models import HistoricalTrade, Player, SeasonCalendar, Standing, Team
from app.ingestion.transactions.parse import classify_conveyance

#: The month rule R7 replaced, kept only as the fallback for a database with no ingested
#: `season_calendar`. It is wrong for the 2020-21 COVID calendar, for draft-night trades
#: filed under the season about to start, and for early-October preseason trades — see the
#: module docstring for the counts.
OFFSEASON_MONTHS = frozenset({7, 8, 9})

DEFAULT_K = 5
MAX_K = 25


@dataclass(frozen=True)
class SeasonWindow:
    """One season's played boundary, as ingested."""

    season: str
    first_game: date
    last_game: date


def _previous_season(season: str) -> str:
    start = int(season.split("-")[0]) - 1
    return f"{start}-{str(start + 1)[-2:]}"


def feature_season_by_month(season: str, when: date) -> str:
    """The pre-R7 rule. Retained as the fallback, and as the thing tests compare against."""
    return _previous_season(season) if when.month in OFFSEASON_MONTHS else season


def feature_season_for(
    season: str, when: date, calendar: list[SeasonWindow] | None = None
) -> tuple[str, bool]:
    """The season whose production describes a trade made on `when`, and whether it was
    made during that season.

    With a calendar the answer comes from what had been played: the season in progress if
    the trade falls inside one, otherwise the most recently completed. Without one the
    month rule answers, which is why the response reports which of the two was used.

    `season` — the league year the source filed the trade under — is used only as the
    fallback's anchor. The calendar path deliberately ignores it: Basketball-Reference
    files draft-night trades under the season about to start, and that label is exactly
    what was producing the look-ahead.
    """
    if not calendar:
        by_month = feature_season_by_month(season, when)
        return by_month, when.month not in OFFSEASON_MONTHS
    for window in calendar:
        if window.first_game <= when <= window.last_game:
            return window.season, True
    completed = [w for w in calendar if w.last_game < when]
    if completed:
        return max(completed, key=lambda w: w.last_game).season, False
    # The trade predates every ingested season. There is no production to describe it
    # with, and naming one anyway is how a side acquires a value it cannot support; the
    # earliest known season is returned so the side sorts out of the scored window and is
    # counted as unrankable rather than silently priced.
    return _previous_season(min(calendar, key=lambda w: w.first_game).season), False


@dataclass
class PlayerSeasonRow:
    tei: float
    minutes: float | None
    age: float | None


class ComparableTradeService:
    """Corpus assembly and retrieval. One instance per request."""

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self._season_rows: dict[tuple[str, str], PlayerSeasonRow] | None = None
        self._seasons_by_player: dict[str, set[str]] | None = None
        self._win_pct: dict[tuple[str, str], float] | None = None
        self._calendar: list[SeasonWindow] | None = None
        self._corpus: list[TradeSide] | None = None
        self._scales: dict[str, float] | None = None
        self._teams: dict[str, Team] | None = None

    # ------------------------------------------------------------- season scoring

    def _load_season_scores(self) -> None:
        """Score every player-season with the index TEI is defined on.

        Deliberately **not** `player_impact_estimates`: those are the recency-weighted
        window, which cannot describe a 2024-25 trade. `add_zscores` standardizes within
        season, so a season's scores do not move when another season is present — which is
        what lets one table serve every year in the corpus.
        """
        frame = build_player_season_features(self.db)
        rows: dict[tuple[str, str], PlayerSeasonRow] = {}
        seasons: dict[str, set[str]] = {}
        if not frame.empty:
            scored = add_zscores(frame.copy())
            scored["season_tei"] = baseline_index(scored)
            for row in scored.itertuples():
                minutes = getattr(row, "MIN", None)
                age = getattr(row, "AGE", None)
                rows[(row.player_id, row.season)] = PlayerSeasonRow(
                    tei=float(row.season_tei),
                    minutes=float(minutes) if minutes is not None and pd.notna(minutes) else None,
                    age=float(age) if age is not None and pd.notna(age) else None,
                )
                seasons.setdefault(row.player_id, set()).add(row.season)
        self._season_rows = rows
        self._seasons_by_player = seasons

    def season_rows(self) -> dict[tuple[str, str], PlayerSeasonRow]:
        if self._season_rows is None:
            self._load_season_scores()
        assert self._season_rows is not None
        return self._season_rows

    def seasons_by_player(self) -> dict[str, set[str]]:
        if self._seasons_by_player is None:
            self._load_season_scores()
        assert self._seasons_by_player is not None
        return self._seasons_by_player

    def scored_seasons(self) -> set[str]:
        return {season for _, season in self.season_rows()}

    def win_pct(self) -> dict[tuple[str, str], float]:
        if self._win_pct is None:
            self._win_pct = {
                (row.team_id, row.season): float(row.win_pct)
                for row in self.db.scalars(select(Standing)).all()
            }
        return self._win_pct

    def teams(self) -> dict[str, Team]:
        if self._teams is None:
            self._teams = {t.id: t for t in self.db.scalars(select(Team)).all()}
        return self._teams

    def calendar(self) -> list[SeasonWindow]:
        """Ingested season boundaries, newest last. Empty where none has been synced."""
        if self._calendar is None:
            self._calendar = [
                SeasonWindow(row.season, row.first_game_date, row.last_game_date)
                for row in self.db.scalars(
                    select(SeasonCalendar).order_by(SeasonCalendar.first_game_date)
                ).all()
            ]
        return self._calendar

    def feature_season(self, season: str, when: date) -> tuple[str, bool]:
        return feature_season_for(season, when, self.calendar())

    # ----------------------------------------------------------------- leg building

    def _player_leg(
        self, player_id: str | None, name: str, feature_season: str
    ) -> PlayerLeg:
        """One player leg, or a leg that says why it could not be priced.

        Three states, and the difference between the last two is the whole point:

        - the player has a row for the feature season — priced;
        - he has none, and had none in any **earlier** modelled season — he had produced
          nothing at the time of the trade, so zero is a measurement;
        - he has none, but did play before — his value exists and this database cannot
          state it, so the side is withheld rather than understated.
        """
        if player_id is None:
            return PlayerLeg(name=name, player_id=None, no_prior_nba_season=True)
        row = self.season_rows().get((player_id, feature_season))
        if row is not None:
            return PlayerLeg(
                name=name,
                player_id=player_id,
                tei=row.tei,
                minutes=row.minutes,
                age=row.age,
            )
        played_before = any(
            season < feature_season for season in self.seasons_by_player().get(player_id, set())
        )
        return PlayerLeg(
            name=name,
            player_id=player_id,
            no_prior_nba_season=not played_before,
        )

    def _pick_leg(self, draft_year: int, round_number: int, note: str | None) -> PickLeg:
        return PickLeg(
            draft_year=draft_year,
            round_number=round_number,
            conveyance=classify_conveyance(note),
        )

    def _side(
        self,
        *,
        key: str,
        group_key: str | None = None,
        team_id: str | None = None,
        team_abbreviation: str,
        team_name: str | None,
        season: str,
        feature_season: str,
        when: date | None,
        is_in_season: bool,
        n_teams: int,
        counterparties: list[str],
        incoming: list[PlayerLeg],
        outgoing: list[PlayerLeg],
        picks_in: list[PickLeg],
        picks_out: list[PickLeg],
        counterparty_team_ids: list[str],
        cash_involved: bool = False,
        trade_exception_received: bool = False,
        source_text: str = "",
        notes_text: str | None = None,
        unparsed_assets: tuple[str, ...] = (),
    ) -> TradeSide:
        """The single constructor. Query and corpus differ only in their arguments."""
        win = self.win_pct()
        focal_win = win.get((team_id, feature_season)) if team_id else None
        others = [win.get((tid, feature_season)) for tid in counterparty_team_ids]
        known = [w for w in others if w is not None]
        return TradeSide(
            key=key,
            group_key=group_key,
            team_id=team_id,
            team_abbreviation=team_abbreviation,
            team_name=team_name,
            season=season,
            feature_season=feature_season,
            transaction_date=when,
            is_in_season=is_in_season,
            n_teams=n_teams,
            counterparty_abbreviations=tuple(counterparties),
            incoming=tuple(incoming),
            outgoing=tuple(outgoing),
            picks_in=tuple(picks_in),
            picks_out=tuple(picks_out),
            win_pct=focal_win,
            counterparty_win_pct=(sum(known) / len(known)) if known else None,
            cash_involved=cash_involved,
            trade_exception_received=trade_exception_received,
            source_text=source_text,
            notes_text=notes_text,
            unparsed_assets=unparsed_assets,
        )

    # ---------------------------------------------------------------------- corpus

    def corpus(self) -> list[TradeSide]:
        """One side per (completed trade, participating team)."""
        if self._corpus is not None:
            return self._corpus
        trades = self.db.scalars(
            select(HistoricalTrade).order_by(
                HistoricalTrade.transaction_date, HistoricalTrade.source_record_id
            )
        ).all()
        teams = self.teams()
        by_abbr = {t.abbreviation.upper(): t for t in teams.values()}
        sides: list[TradeSide] = []
        for trade in trades:
            feature_season, in_season = self.feature_season(
                trade.season, trade.transaction_date
            )
            participants: list[str] = []
            for asset in trade.assets:
                for abbr in (asset.from_abbreviation, asset.to_abbreviation):
                    if abbr not in participants:
                        participants.append(abbr)
            for abbr in sorted(participants):
                team = by_abbr.get(abbr)
                counterparties = [a for a in sorted(participants) if a != abbr]
                incoming: list[PlayerLeg] = []
                outgoing: list[PlayerLeg] = []
                picks_in: list[PickLeg] = []
                picks_out: list[PickLeg] = []
                cash = False
                for asset in trade.assets:
                    if abbr not in (asset.from_abbreviation, asset.to_abbreviation):
                        continue
                    arriving = asset.to_abbreviation == abbr
                    if asset.asset_type == "player":
                        leg = self._player_leg(
                            asset.player_id, asset.player_name or "unknown", feature_season
                        )
                        (incoming if arriving else outgoing).append(leg)
                    elif asset.asset_type == "pick":
                        pick = self._pick_leg(
                            asset.draft_year or 0, asset.round_number or 0, asset.note_text
                        )
                        (picks_in if arriving else picks_out).append(pick)
                    elif asset.asset_type == "cash":
                        cash = True
                sides.append(
                    self._side(
                        key=f"{trade.source_record_id}|{abbr}",
                        group_key=trade.source_record_id,
                        team_id=team.id if team else None,
                        team_abbreviation=abbr,
                        team_name=team.full_name if team else None,
                        season=trade.season,
                        feature_season=feature_season,
                        when=trade.transaction_date,
                        is_in_season=in_season,
                        n_teams=trade.n_teams,
                        counterparties=counterparties,
                        incoming=incoming,
                        outgoing=outgoing,
                        picks_in=picks_in,
                        picks_out=picks_out,
                        counterparty_team_ids=[
                            by_abbr[a].id for a in counterparties if a in by_abbr
                        ],
                        cash_involved=cash,
                        trade_exception_received=(
                            team is not None and team.id in (trade.trade_exception_team_ids or [])
                        ),
                        source_text=trade.source_text,
                        notes_text=trade.notes_text,
                        unparsed_assets=tuple(trade.unparsed_assets or ()),
                    )
                )
        self._corpus = sides
        return sides

    def rankable_corpus(self) -> list[TradeSide]:
        scored = self.scored_seasons()
        return [s for s in self.corpus() if s.feature_season in scored and s.rankable]

    def scales(self) -> dict[str, float]:
        if self._scales is None:
            self._scales = robust_scales(self.rankable_corpus())
        return self._scales

    # ----------------------------------------------------------------------- query

    def query_side(
        self,
        team_id: str,
        team_ids: list[str],
        player_moves: list[dict],
        pick_moves: list[dict],
        as_of: date | None = None,
    ) -> TradeSide:
        team = self.teams().get(team_id)
        if team is None:
            raise NotFoundError(f"team {team_id} not found")
        when = as_of or date.today()
        season = self.settings.current_season
        feature_season, in_season = self.feature_season(season, when)
        players = {
            p.id: p
            for p in self.db.scalars(
                select(Player).where(
                    Player.id.in_([m["player_id"] for m in player_moves if m.get("player_id")])
                )
            ).all()
        }
        incoming: list[PlayerLeg] = []
        outgoing: list[PlayerLeg] = []
        for move in player_moves:
            player = players.get(move.get("player_id") or "")
            if player is None:
                continue
            leg = self._player_leg(player.id, player.full_name, feature_season)
            if move["to_team_id"] == team_id:
                incoming.append(leg)
            elif move["from_team_id"] == team_id:
                outgoing.append(leg)
        picks_in: list[PickLeg] = []
        picks_out: list[PickLeg] = []
        for move in pick_moves:
            pick = self._pick_leg(
                int(move.get("draft_year") or 0),
                int(move.get("round_number") or 0),
                move.get("protections"),
            )
            if move["to_team_id"] == team_id:
                picks_in.append(pick)
            elif move["from_team_id"] == team_id:
                picks_out.append(pick)
        teams = self.teams()
        counterparty_ids = [t for t in team_ids if t != team_id]
        return self._side(
            key="query",
            team_id=team_id,
            team_abbreviation=team.abbreviation,
            team_name=team.full_name,
            season=season,
            feature_season=feature_season,
            when=when,
            is_in_season=in_season,
            n_teams=len(team_ids),
            counterparties=[
                teams[t].abbreviation for t in counterparty_ids if t in teams
            ],
            incoming=incoming,
            outgoing=outgoing,
            picks_in=picks_in,
            picks_out=picks_out,
            counterparty_team_ids=counterparty_ids,
            source_text="proposed trade",
        )

    # -------------------------------------------------------------------- retrieval

    def find(
        self,
        team_id: str,
        team_ids: list[str],
        player_moves: list[dict],
        pick_moves: list[dict],
        k: int = DEFAULT_K,
        weights: dict[str, float] | None = None,
        as_of: date | None = None,
    ) -> dict:
        query = self.query_side(team_id, team_ids, player_moves, pick_moves, as_of=as_of)
        corpus = self.rankable_corpus()
        coverage = self.coverage()
        if not (query.incoming or query.outgoing or query.picks_in or query.picks_out):
            # Nothing moves on this side, so there is no decision to find precedent for.
            # Without the guard the retrieval answers honestly and uselessly: an empty
            # query matched cash-only trades at 94 % similarity, because both sides moved
            # nothing of value, and that reads as nonsense rather than as evidence.
            return {
                "available": False,
                "unavailable_reason": (
                    f"nothing moves to or from {query.team_abbreviation} in this trade, "
                    "so there is no decision to find a precedent for"
                ),
                "query": _query_payload(query),
                "coverage": coverage,
                "comparables": [],
            }
        if not query.rankable:
            return {
                "available": False,
                "unavailable_reason": (
                    "the proposed trade contains players this database has no "
                    f"{query.feature_season} production for, so its own package value "
                    "cannot be stated"
                ),
                "unmodelled_players": list(query.unmodelled_players),
                "query": _query_payload(query),
                "coverage": coverage,
                "comparables": [],
            }
        if not corpus:
            return {
                "available": False,
                "unavailable_reason": (
                    "no completed trade in this database has a feature season with "
                    "modelled player production; run `make import-transactions`"
                ),
                "query": _query_payload(query),
                "coverage": coverage,
                "comparables": [],
            }
        neighbours = rank(query, corpus, self.scales(), weights, k=min(max(k, 1), MAX_K))
        return {
            "available": True,
            "query": _query_payload(query),
            "coverage": coverage,
            "weights": weights or DIMENSION_WEIGHTS,
            "dimensions": {
                name: {"features": list(features), "label": DIMENSION_LABELS[name]}
                for name, features in FEATURE_DIMENSIONS.items()
            },
            "not_scored": _NOT_SCORED,
            "comparables": [
                _neighbour_payload(query, neighbour) for neighbour in neighbours
            ],
        }

    def coverage(self) -> dict:
        corpus = self.corpus()
        scored = self.scored_seasons()
        in_window = [s for s in corpus if s.feature_season in scored]
        blocked = [s for s in in_window if not s.rankable]
        trades = {s.key.split("|")[0] for s in corpus}
        calendar = self.calendar()
        return {
            "trades_ingested": len(trades),
            "seasons_ingested": sorted({s.season for s in corpus}),
            "sides_total": len(corpus),
            "sides_in_modelled_window": len(in_window),
            "sides_rankable": len(in_window) - len(blocked),
            "sides_blocked_by_unmodelled_players": len(blocked),
            "trades_rankable": len({s.group_key for s in in_window if s.rankable}),
            "modelled_seasons": sorted(scored),
            #: Which rule decided every feature season on this response. False means no
            #: season boundary has been ingested and the calendar month answered instead,
            #: which mis-describes draft-night, preseason and 2020-21 November trades.
            "calendar_backed": bool(calendar),
            "seasons_with_calendar": [w.season for w in calendar],
            "note": (
                "A side is ranked only where this database can state the on-court value "
                "of every player in it. Player production is held for "
                f"{', '.join(sorted(scored))}, so trades whose feature season falls "
                "outside that window are stored and retrievable but not ranked."
            )
            + (
                ""
                if calendar
                else " No season calendar has been ingested, so each trade's feature "
                "season was decided from its calendar month; run "
                "`make sync-season-calendar`."
            ),
        }


_NOT_SCORED = [
    {
        "field": "salary",
        "reason": (
            "no source in this repository carries a historical contract, so a completed "
            "trade's money is unavailable for every side in the corpus"
        ),
    },
    {
        "field": "cash and trade exceptions",
        "reason": (
            "the corpus states both and a proposed trade in this product states neither, "
            "so scoring them would penalize the 37 % of completed trades that include one"
        ),
    },
    {
        "field": "what happened next",
        "reason": (
            "nothing here reads the outcome. A comparable is evidence about precedent, "
            "not about consequence"
        ),
    },
]


def _leg_payload(leg: PlayerLeg) -> dict:
    return {
        "name": leg.name,
        "player_id": leg.player_id,
        "tei": round(leg.tei, 2) if leg.tei is not None else None,
        "minutes": round(leg.minutes, 1) if leg.minutes is not None else None,
        "age": round(leg.age, 1) if leg.age is not None else None,
        "no_prior_nba_season": leg.no_prior_nba_season,
    }


def _pick_payload(pick: PickLeg) -> dict:
    return {
        "draft_year": pick.draft_year,
        "round_number": pick.round_number,
        "conveyance": pick.conveyance,
    }


def _side_payload(side: TradeSide) -> dict:
    features = side.features()
    return {
        "key": side.key,
        "team_id": side.team_id,
        "team_abbreviation": side.team_abbreviation,
        "team_name": side.team_name,
        "counterparties": list(side.counterparty_abbreviations),
        "season": side.season,
        "feature_season": side.feature_season,
        "transaction_date": side.transaction_date.isoformat() if side.transaction_date else None,
        "is_in_season": side.is_in_season,
        "n_teams": side.n_teams,
        "incoming": [_leg_payload(leg) for leg in side.incoming],
        "outgoing": [_leg_payload(leg) for leg in side.outgoing],
        "picks_in": [_pick_payload(p) for p in side.picks_in],
        "picks_out": [_pick_payload(p) for p in side.picks_out],
        "win_pct": side.win_pct,
        "counterparty_win_pct": side.counterparty_win_pct,
        "features": {k: (round(v, 4) if v is not None else None) for k, v in features.items()},
        "no_prior_season_players": list(side.no_prior_season_players),
    }


def _query_payload(side: TradeSide) -> dict:
    payload = _side_payload(side)
    payload["unmodelled_players"] = list(side.unmodelled_players)
    payload["rankable"] = side.rankable
    return payload


def _neighbour_payload(query: TradeSide, neighbour: Neighbour) -> dict:
    side = neighbour.side
    comparison = neighbour.comparison
    payload = _side_payload(side)
    payload.update(
        {
            "similarity": round(comparison.similarity, 4),
            "distance": round(comparison.distance, 4),
            "why": explain(query, neighbour),
            "dimension_similarity": {
                d.name: {
                    "similarity": round(d.similarity, 4),
                    "weight": d.weight,
                    "features": {
                        name: {
                            "query": values["query"],
                            "comparable": values["comparable"],
                            "similarity": round(1.0 - (values["distance"] or 0.0), 4),
                        }
                        for name, values in d.features.items()
                    },
                }
                for d in comparison.dimensions
            },
            "contributions": [
                {"dimension": name, "share": round(share, 4)}
                for name, share in comparison.contributions()
            ],
            "dimensions_unavailable": comparison.dimensions_unavailable,
            "features_unavailable": comparison.features_unavailable,
            "reported_not_scored": {
                "cash_involved": side.cash_involved,
                "trade_exception_received": side.trade_exception_received,
            },
            "source_text": side.source_text,
            "notes_text": side.notes_text,
            "unparsed_assets": list(side.unparsed_assets),
        }
    )
    return payload


def compare_sides(
    query: TradeSide, other: TradeSide, scales: dict[str, float], weights: dict[str, float] | None
) -> Any:
    """Thin re-export so callers do not import the analytics module for one function."""
    return compare(query, other, scales, weights)
