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
            coverage_before = team.coverage_before
            coverage_after = team.coverage_after
            per_team[team.team_id] = {
                "abbreviation": team.abbreviation,
                "status": overall_status(team_results),
                "outgoing_salary": team.outgoing_salary,
                "incoming_salary": team.incoming_salary,
                # `payroll_*` stay verified-only: they are `None` unless every rostered
                # player is priced, and they are what a caller may compare to a threshold.
                "payroll_before": team.payroll_before,
                "payroll_after": team.payroll_after,
                "apron_status_before": team.apron_status(team.payroll_before, context.params),
                "apron_status_after": team.apron_status(team.payroll_after, context.params),
                # `payroll_known_*` are the R2c disclosure: a lower bound that must never
                # be rendered without the coverage beside it.
                "payroll_known_before": team.payroll_known_before,
                "payroll_known_after": team.payroll_known_after,
                "payroll_coverage_before": coverage_before.as_dict() if coverage_before else None,
                "payroll_coverage_after": coverage_after.as_dict() if coverage_after else None,
                "payroll_coverage_note": (
                    coverage_before.disclosure() if coverage_before else None
                ),
                "apron_status_at_least_before": team.apron_status_at_least(
                    coverage_before, context.params
                ),
                "apron_status_at_least_after": team.apron_status_at_least(
                    coverage_after, context.params
                ),
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
