"""Trade legality engine: runs every registered rule and derives per-team and overall
statuses under the honesty standard (see context.overall_status)."""

from dataclasses import asdict

from .context import LegalityStatus, RuleResult, TradeContext, overall_status
from .rules import all_rules


class TradeLegalityEngine:
    def __init__(self) -> None:
        self.rules = all_rules()

    def evaluate(self, context: TradeContext) -> dict:
        results: list[RuleResult] = []
        for rule in self.rules:
            results.extend(rule.evaluate(context))

        per_team: dict[str, dict] = {}
        for team in context.teams:
            team_results = [r for r in results if r.team_id in (team.team_id, None)]
            per_team[team.team_id] = {
                "abbreviation": team.abbreviation,
                "status": overall_status(team_results),
                "outgoing_salary": team.outgoing_salary,
                "incoming_salary": team.incoming_salary,
                "payroll_before": team.payroll_before,
                "payroll_after": team.payroll_after,
                "apron_status_before": team.apron_status(team.payroll_before, context.params),
                "apron_status_after": team.apron_status(team.payroll_after, context.params),
                "roster_before": team.roster_count_before,
                "roster_after": team.roster_count_after,
            }

        status: LegalityStatus = overall_status(results)
        return {
            "league_year": context.league_year,
            "overall_status": status,
            "teams": per_team,
            "rule_results": [asdict(r) for r in results],
            "cap_parameters_source": context.params.source_name,
            "contract_provider_configured": context.contract_provider_configured,
        }
