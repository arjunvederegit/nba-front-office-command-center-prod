"""Team payroll summaries. When contract data is absent the summary says so
explicitly — no partial sums presented as payroll."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cba.builder import _player_salary, load_cap_params
from app.config import get_settings
from app.core.errors import DataUnavailableError
from app.db.models import RosterEntry, Team
from app.integrations.contracts import get_contract_provider


def team_payroll_summary(db: Session, team: Team) -> dict:
    settings = get_settings()
    league_year = settings.cap_league_year
    season = settings.current_season
    try:
        params = load_cap_params(db, league_year)
    except DataUnavailableError:
        params = None

    entries = db.scalars(
        select(RosterEntry).where(
            RosterEntry.team_id == team.id, RosterEntry.season == season, RosterEntry.is_current
        )
    ).all()

    players = []
    total = 0
    known = 0
    for entry in entries:
        salary, contract = _player_salary(db, entry.player_id, league_year)
        if salary is not None:
            total += salary
            known += 1
        players.append(
            {
                "player_id": entry.player_id,
                "name": entry.player.full_name,
                "salary": salary,
                "contract_type": contract.contract_type if contract else None,
                "source_name": contract.source_name if contract else None,
                "source_date": contract.source_date.isoformat()
                if contract and contract.source_date
                else None,
            }
        )

    complete = bool(entries) and known == len(entries)
    payroll = total if complete else None
    summary: dict = {
        "league_year": league_year,
        "roster_size": len(entries),
        "players_with_salary": known,
        "payroll": payroll,
        "payroll_available": complete,
        "players": players,
        "contract_provider_configured": get_contract_provider() is not None,
    }
    if not complete:
        summary["unavailable_reason"] = (
            "Contract data unavailable from the configured provider. Payroll, tax and "
            "apron status cannot be computed."
            if get_contract_provider() is not None
            else "No contract provider is configured (nba_api does not supply contracts). "
            "See data/contracts/README.md to enable one."
        )
    if params and payroll is not None:
        summary["cap_context"] = {
            "salary_cap": params.salary_cap,
            "luxury_tax": params.luxury_tax,
            "first_apron": params.first_apron,
            "second_apron": params.second_apron,
            "room_below_tax": params.luxury_tax - payroll,
            "cap_source": params.source_name,
        }
    return summary
