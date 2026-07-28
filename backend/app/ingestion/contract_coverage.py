"""What a contract snapshot actually covers, measured from the **roster** side.

The metric that matters is not the one the import naturally reports. A BBRef-side match
rate answers "how many rows in the file did we recognise", and can read 98 % while the
question the product needs answered — "can we compute payroll for this team" — is 60 %.

`_team_payroll` is all-or-nothing by design: a partial sum understates payroll and
silently skews apron status. That makes coverage a cliff, not a slope. Measured
sensitivity on the live 530-row roster:

    roster players missing a 2026-27 salary → teams with a payroll
     1 %  → 26/30      2 %  → 21/30      5 %  → 10/30
    10 %  →  4/30     20 %  →  0/30

An offseason snapshot plausibly misses 25–40 % (expired contracts) → **zero teams with
payroll**, while a BBRef-side match rate reports success the whole time. This module
computes the roster-side number so an import can be judged before it is trusted, and it
runs whether or not a provider is configured.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cba import resolver
from app.db.models import Contract, ContractYear, RosterEntry, Team


def contract_coverage(db: Session, season: str, league_year: str) -> dict:
    """Roster-side coverage for `league_year`, plus the shape of what is on file."""
    entries = list(
        db.scalars(
            select(RosterEntry).where(
                RosterEntry.season == season, RosterEntry.is_current
            )
        ).all()
    )
    teams = {t.id: t.abbreviation for t in db.scalars(select(Team)).all()}
    by_team: dict[str, list[RosterEntry]] = {}
    for entry in entries:
        by_team.setdefault(entry.team_id, []).append(entry)

    resolved = resolver.salaries(db, [e.player_id for e in entries], league_year)
    with_salary = {pid for pid, (salary, _) in resolved.items() if salary is not None}

    teams_complete = 0
    incomplete: list[dict] = []
    for team_id, roster in sorted(by_team.items(), key=lambda kv: teams.get(kv[0], kv[0])):
        missing = [e.player_id for e in roster if e.player_id not in with_salary]
        if not missing:
            teams_complete += 1
        else:
            incomplete.append(
                {
                    "team": teams.get(team_id, team_id),
                    "roster_size": len(roster),
                    "missing": len(missing),
                }
            )

    # Which league years the snapshot actually carries. An import that has every player
    # but only for 2025-26 is useless for a 2026-27 cap check, and would otherwise look
    # like a complete success.
    seasons_present = sorted(
        {
            row
            for (row,) in db.execute(select(ContractYear.season).distinct()).all()
            if row
        }
    )
    contracts_on_file = db.scalar(select(Contract).limit(1)) is not None

    total = len(entries)
    covered = len([e for e in entries if e.player_id in with_salary])
    return {
        "season": season,
        "cap_league_year": league_year,
        "roster_players_total": total,
        "roster_players_with_salary_for_cap_league_year": covered,
        "roster_coverage_share": round(covered / total, 4) if total else None,
        "teams_total": len(by_team),
        "teams_with_complete_payroll": teams_complete,
        "teams_incomplete": incomplete,
        "seasons_present_in_snapshot": seasons_present,
        "cap_league_year_present_in_snapshot": league_year in seasons_present,
        "contracts_on_file": contracts_on_file,
    }


def roster_side_unmatched(
    db: Session, season: str, league_year: str, limit: int = 100
) -> list[dict]:
    """Rostered players with no salary for `league_year` — the list that matters.

    The import's own `unmatched_players` is the *provider's* side: names in the file that
    no player matched. It says nothing about a rostered player the file never mentioned,
    which is exactly the case that makes payroll unavailable.
    """
    entries = list(
        db.scalars(
            select(RosterEntry).where(
                RosterEntry.season == season, RosterEntry.is_current
            )
        ).all()
    )
    resolved = resolver.salaries(db, [e.player_id for e in entries], league_year)
    teams = {t.id: t.abbreviation for t in db.scalars(select(Team)).all()}
    players = resolver.players(db, [e.player_id for e in entries])
    rows = [
        {
            "team": teams.get(entry.team_id, entry.team_id),
            "player": players[entry.player_id].full_name
            if entry.player_id in players
            else entry.player_id,
            "reason": "no contract on file"
            if resolved[entry.player_id][1] is None
            else f"contract on file but no {league_year} year",
        }
        for entry in entries
        if resolved[entry.player_id][0] is None
    ]
    rows.sort(key=lambda r: (r["team"], r["player"]))
    return rows[:limit]


def summarize(coverage: dict, unmatched: Iterable[dict]) -> str:
    """One line an operator can act on."""
    if not coverage["contracts_on_file"]:
        return (
            "No contracts on file. Salary matching, payroll and apron status stay "
            "unavailable product-wide."
        )
    if not coverage["cap_league_year_present_in_snapshot"]:
        return (
            f"The snapshot carries {coverage['seasons_present_in_snapshot']} but not "
            f"{coverage['cap_league_year']}, which is the league year trade legality is "
            "evaluated under. No team will have a payroll."
        )
    share = coverage["roster_coverage_share"] or 0
    return (
        f"{coverage['roster_players_with_salary_for_cap_league_year']}/"
        f"{coverage['roster_players_total']} rostered players ({share:.1%}) have a "
        f"{coverage['cap_league_year']} salary; "
        f"{coverage['teams_with_complete_payroll']}/{coverage['teams_total']} teams have "
        f"a computable payroll. {len(list(unmatched))} rostered players are listed as "
        "uncovered."
    )
