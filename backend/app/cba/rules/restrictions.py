"""Player-level trade restrictions that depend on contract detail.

Each rule evaluates honestly against available data: with no contract provider these
return `unavailable` for affected players rather than pretending the restriction
doesn't exist."""

from datetime import date, timedelta

from ..context import RuleResult, TradeContext

CBA_REF = "2023 CBA Art. VII (trade restrictions)"


class RecentlySignedRule:
    code = "RECENTLY_SIGNED"
    description = "Recently signed free agents cannot be traded for 3 months / until Dec 15"

    def __init__(self, today: date | None = None):
        self.today = today or date.today()

    def evaluate(self, context: TradeContext) -> list[RuleResult]:
        results = []
        for team in context.teams:
            for player in team.outgoing:
                if player.signed_date is None:
                    if not context.contract_provider_configured:
                        continue  # covered by SALARY_DATA_AVAILABLE; avoid noise
                    results.append(
                        RuleResult(
                            rule_code=self.code,
                            status="unavailable",
                            team_id=team.team_id,
                            message=f"Signing date unknown for {player.name}; the recently-signed "
                            "restriction cannot be checked.",
                            source_reference=CBA_REF,
                        )
                    )
                    continue
                three_months = player.signed_date + timedelta(days=90)
                season_gate = date(player.signed_date.year, 12, 15)
                eligible_on = max(three_months, season_gate) if player.signed_date.month >= 7 else three_months
                restricted = self.today < eligible_on
                results.append(
                    RuleResult(
                        rule_code=self.code,
                        status="fail" if restricted else "pass",
                        team_id=team.team_id,
                        message=(
                            f"{player.name} signed {player.signed_date.isoformat()} and cannot be "
                            f"traded before {eligible_on.isoformat()}."
                            if restricted
                            else f"{player.name} is outside the recently-signed restriction window."
                        ),
                        calculation={
                            "signed_date": player.signed_date.isoformat(),
                            "eligible_on": eligible_on.isoformat(),
                        },
                        source_reference=CBA_REF,
                        confidence="medium",
                    )
                )
        return results


class NoTradeClauseRule:
    code = "NO_TRADE_CLAUSE"
    description = "Players with a no-trade clause must consent — surfaced as a warning"

    def evaluate(self, context: TradeContext) -> list[RuleResult]:
        results = []
        for team in context.teams:
            for player in team.outgoing:
                if player.no_trade_clause:
                    results.append(
                        RuleResult(
                            rule_code=self.code,
                            status="warning",
                            team_id=team.team_id,
                            message=f"{player.name} has a no-trade clause and must consent to this trade.",
                            source_reference=CBA_REF,
                        )
                    )
        return results


class TwoWayExclusionRule:
    code = "TWO_WAY_EXCLUSION"
    description = "Two-way contracts do not count toward salary matching"

    def evaluate(self, context: TradeContext) -> list[RuleResult]:
        results = []
        for team in context.teams:
            two_way = [
                p.name for p in team.outgoing + team.incoming if p.contract_type == "two-way"
            ]
            if two_way:
                results.append(
                    RuleResult(
                        rule_code=self.code,
                        status="pass",
                        team_id=team.team_id,
                        message=f"Two-way contracts excluded from salary matching: {', '.join(two_way)}.",
                        calculation={"two_way_players": two_way},
                        source_reference="2023 CBA Art. VII §8 (two-way)",
                    )
                )
        return results
