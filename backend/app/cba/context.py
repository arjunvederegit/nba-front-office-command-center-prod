"""Trade context and rule result types.

The honesty standard (docs/cba-rule-coverage.md):
- verified_legal      — every implemented required rule passed with current data
- verified_illegal    — at least one implemented rule failed
- conditionally_valid — implemented rules passed but required data was unavailable
- not_evaluated       — insufficient data to run any meaningful rule

A trade is NEVER labeled legal when only partial validation was possible."""

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Protocol

RuleStatus = Literal["pass", "fail", "warning", "unavailable"]
LegalityStatus = Literal["verified_legal", "verified_illegal", "conditionally_valid", "not_evaluated"]


@dataclass
class PlayerAsset:
    player_id: str
    name: str
    from_team_id: str
    to_team_id: str
    salary: int | None = None  # None = contract data unavailable (never guessed)
    contract_type: str | None = None
    signed_date: date | None = None
    no_trade_clause: bool | None = None


@dataclass
class PickAsset:
    from_team_id: str
    to_team_id: str
    draft_year: int
    round_number: int
    protections: str | None
    is_hypothetical: bool


@dataclass
class CapParams:
    league_year: str
    salary_cap: int
    luxury_tax: int
    first_apron: int
    second_apron: int
    minimum_team_salary: int
    source_name: str = ""
    # Expanded TPE anchors for the 2025-26 league year; the CBA scales these with the
    # cap, so other years derive by the cap ratio (documented in cba-rule-coverage.md).
    tpe_band1_max_2025: int = 8_846_000
    tpe_band2_add_2025: int = 9_096_000
    tpe_band2_max_2025: int = 35_384_000
    salary_cap_2025: int = 154_647_000
    allowance: int = 250_000

    @property
    def cap_ratio(self) -> float:
        return self.salary_cap / self.salary_cap_2025

    @property
    def tpe_band1_max(self) -> float:
        return self.tpe_band1_max_2025 * self.cap_ratio

    @property
    def tpe_band2_add(self) -> float:
        return self.tpe_band2_add_2025 * self.cap_ratio

    @property
    def tpe_band2_max(self) -> float:
        return self.tpe_band2_max_2025 * self.cap_ratio


@dataclass
class TeamContext:
    team_id: str
    abbreviation: str
    name: str
    roster_count_before: int
    outgoing: list[PlayerAsset] = field(default_factory=list)
    incoming: list[PlayerAsset] = field(default_factory=list)
    picks_out: list[PickAsset] = field(default_factory=list)
    picks_in: list[PickAsset] = field(default_factory=list)
    payroll_before: int | None = None  # None when contract data is incomplete
    payroll_players_known: int = 0
    payroll_players_total: int = 0

    @property
    def roster_count_after(self) -> int:
        return self.roster_count_before - len(self.outgoing) + len(self.incoming)

    @property
    def salaries_known(self) -> bool:
        return all(p.salary is not None for p in self.outgoing + self.incoming)

    @property
    def outgoing_salary(self) -> int | None:
        if any(p.salary is None for p in self.outgoing):
            return None
        return sum(p.salary or 0 for p in self.outgoing if (p.contract_type or "standard") != "two-way")

    @property
    def incoming_salary(self) -> int | None:
        if any(p.salary is None for p in self.incoming):
            return None
        return sum(p.salary or 0 for p in self.incoming if (p.contract_type or "standard") != "two-way")

    @property
    def payroll_after(self) -> int | None:
        if self.payroll_before is None or self.outgoing_salary is None or self.incoming_salary is None:
            return None
        return self.payroll_before - self.outgoing_salary + self.incoming_salary

    @property
    def aggregates_salaries(self) -> bool:
        """Sending 2+ standard contracts combined for matching purposes."""
        return len([p for p in self.outgoing if (p.contract_type or "standard") != "two-way"]) >= 2

    def apron_status(self, payroll: int | None, params: CapParams) -> str | None:
        if payroll is None:
            return None
        if payroll > params.second_apron:
            return "above_second_apron"
        if payroll > params.first_apron:
            return "above_first_apron"
        if payroll > params.luxury_tax:
            return "above_tax"
        return "below_tax"


@dataclass
class TradeContext:
    league_year: str
    params: CapParams
    teams: list[TeamContext]
    contract_provider_configured: bool = False

    def team(self, team_id: str) -> TeamContext:
        for t in self.teams:
            if t.team_id == team_id:
                return t
        raise KeyError(team_id)


@dataclass
class RuleResult:
    rule_code: str
    status: RuleStatus
    team_id: str | None
    message: str
    calculation: dict = field(default_factory=dict)
    source_reference: str = ""
    confidence: Literal["high", "medium", "low"] = "high"


class TradeRule(Protocol):
    code: str
    description: str

    def evaluate(self, context: TradeContext) -> list[RuleResult]: ...


def overall_status(results: list[RuleResult]) -> LegalityStatus:
    evaluated = [r for r in results if r.status in ("pass", "fail", "warning")]
    if any(r.status == "fail" for r in results):
        return "verified_illegal"
    if not evaluated:
        return "not_evaluated"
    if any(r.status == "unavailable" for r in results):
        return "conditionally_valid"
    return "verified_legal"
