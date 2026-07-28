"""Builds a TradeContext from database state for the legality engine."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import DataUnavailableError, InvalidTradeError, NotFoundError
from app.db.models import (
    Contract,
    ContractYear,
    LeagueCapParameters,
    Player,
    RosterEntry,
    Team,
)
from app.integrations.contracts import get_contract_provider

from .context import CapParams, PickAsset, PlayerAsset, TeamContext, TradeContext


def load_cap_params(db: Session, league_year: str) -> CapParams:
    row = db.scalar(
        select(LeagueCapParameters).where(LeagueCapParameters.league_year == league_year)
    )
    if row is None:
        raise DataUnavailableError(
            f"No cap parameters loaded for league year {league_year}; run `make seed-config`."
        )
    return CapParams(
        league_year=row.league_year,
        salary_cap=row.salary_cap,
        luxury_tax=row.luxury_tax,
        first_apron=row.first_apron,
        second_apron=row.second_apron,
        minimum_team_salary=row.minimum_team_salary,
        source_name=row.source_name,
    )


def _player_salary(
    db: Session, player_id: str, league_year: str
) -> tuple[int | None, Contract | None]:
    contract = db.scalar(select(Contract).where(Contract.player_id == player_id))
    if contract is None:
        return None, None
    year = db.scalar(
        select(ContractYear).where(
            ContractYear.contract_id == contract.id, ContractYear.season == league_year
        )
    )
    return (year.salary if year else None), contract


def _team_payroll(
    db: Session, team_id: str, season: str, league_year: str
) -> tuple[int | None, int, int]:
    """(payroll or None, players_with_known_salary, roster_size). Payroll is only
    reported when every rostered player has a known salary — partial sums would
    understate payroll and silently skew apron status."""
    entries = db.scalars(
        select(RosterEntry).where(
            RosterEntry.team_id == team_id, RosterEntry.season == season, RosterEntry.is_current
        )
    ).all()
    total = 0
    known = 0
    for entry in entries:
        salary, _ = _player_salary(db, entry.player_id, league_year)
        if salary is not None:
            total += salary
            known += 1
    if entries and known == len(entries):
        return total, known, len(entries)
    return None, known, len(entries)


def _validate_player_moves(db: Session, player_moves: list[dict], season: str) -> None:
    """Reject trades that cannot exist, before any of them is scored.

    Both checks need a database session, so neither can live in a Pydantic
    `field_validator` — and `trades.py` reconstructs saved trades from stored
    `trade_assets` without touching a request model at all, so a validator there would
    also leave every already-persisted trade unvalidated. `build_trade_context` is the
    one place every path passes through.

    QA-2: a player could be "acquired" by the team that already rosters them, landing in
    `after_cards` twice and producing +0.45 wins for acquiring your own player.
    QA-3: an identical move listed twice was counted twice, flipping
    `aggregates_salaries` and shifting `roster_after` by two.
    """
    seen: set[str] = set()
    duplicates: list[str] = []
    for move in player_moves:
        player_id = move["player_id"]
        if player_id in seen:
            duplicates.append(player_id)
        seen.add(player_id)
    if duplicates:
        names = _player_names(db, duplicates)
        raise InvalidTradeError(
            "the same player appears in more than one move: " + ", ".join(names)
        )

    if not player_moves:
        return

    rostered = {
        (entry.player_id, entry.team_id)
        for entry in db.scalars(
            select(RosterEntry).where(
                RosterEntry.player_id.in_([m["player_id"] for m in player_moves]),
                RosterEntry.season == season,
                RosterEntry.is_current,
            )
        ).all()
    }
    known_players = {player_id for player_id, _ in rostered}
    phantom: list[str] = []
    for move in player_moves:
        player_id = move["player_id"]
        # A player absent from every current roster is an unknown-roster case, not a
        # phantom move: the trade may be legitimate against data we do not hold, and
        # refusing it would block every offseason free agent. Only assert the negative
        # when we can see where the player actually is.
        if player_id in known_players and (player_id, move["from_team_id"]) not in rostered:
            phantom.append(player_id)
    if phantom:
        names = _player_names(db, phantom)
        raise InvalidTradeError(
            "these players are not on the roster they are being traded from: "
            + ", ".join(names)
        )


def _player_names(db: Session, player_ids: list[str]) -> list[str]:
    rows = db.scalars(select(Player).where(Player.id.in_(player_ids))).all()
    by_id = {p.id: p.full_name for p in rows}
    return [by_id.get(pid, pid) for pid in dict.fromkeys(player_ids)]


def build_trade_context(
    db: Session,
    team_ids: list[str],
    player_moves: list[dict],
    pick_moves: list[dict] | None = None,
    league_year: str | None = None,
) -> TradeContext:
    """player_moves: [{player_id, from_team_id, to_team_id}]
    pick_moves: [{from_team_id, to_team_id, draft_year, round_number, protections, is_hypothetical}]
    """
    settings = get_settings()
    league_year = league_year or settings.cap_league_year
    season = settings.current_season
    params = load_cap_params(db, league_year)

    _validate_player_moves(db, player_moves, season)

    contexts: dict[str, TeamContext] = {}
    for team_id in team_ids:
        team = db.get(Team, team_id)
        if team is None:
            raise NotFoundError(f"Unknown team id {team_id}")
        payroll, known, total = _team_payroll(db, team_id, season, league_year)
        roster_count = total
        contexts[team_id] = TeamContext(
            team_id=team_id,
            abbreviation=team.abbreviation,
            name=team.full_name,
            roster_count_before=roster_count,
            payroll_before=payroll,
            payroll_players_known=known,
            payroll_players_total=total,
        )

    for move in player_moves:
        player = db.get(Player, move["player_id"])
        if player is None:
            raise NotFoundError(f"Unknown player id {move['player_id']}")
        salary, contract = _player_salary(db, player.id, league_year)
        asset = PlayerAsset(
            player_id=player.id,
            name=player.full_name,
            from_team_id=move["from_team_id"],
            to_team_id=move["to_team_id"],
            salary=salary,
            contract_type=contract.contract_type if contract else None,
            signed_date=contract.signed_date if contract else None,
            no_trade_clause=contract.no_trade_clause if contract else None,
        )
        if move["from_team_id"] in contexts:
            contexts[move["from_team_id"]].outgoing.append(asset)
        if move["to_team_id"] in contexts:
            contexts[move["to_team_id"]].incoming.append(asset)

    for move in pick_moves or []:
        pick = PickAsset(
            from_team_id=move["from_team_id"],
            to_team_id=move["to_team_id"],
            draft_year=move["draft_year"],
            round_number=move["round_number"],
            protections=move.get("protections"),
            is_hypothetical=bool(move.get("is_hypothetical", True)),
        )
        if move["from_team_id"] in contexts:
            contexts[move["from_team_id"]].picks_out.append(pick)
        if move["to_team_id"] in contexts:
            contexts[move["to_team_id"]].picks_in.append(pick)

    return TradeContext(
        league_year=league_year,
        params=params,
        teams=[contexts[tid] for tid in team_ids],
        contract_provider_configured=get_contract_provider() is not None,
    )
