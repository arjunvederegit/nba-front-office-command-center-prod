"""Salary matching and apron rules (2023 CBA, in full effect from 2024-25).

Sources: 2023 NBA-NBPA CBA Article VII; thresholds cross-checked against
cbaguide.com/transactions/trades/tpe and Hoops Rumors' traded-player-exception
glossary for the 2025-26 league year. Expanded-TPE dollar anchors scale with the
salary cap per the CBA; other league years derive by the cap ratio.

Every salary rule returns `unavailable` — never a guess — when contract data is
missing for any involved player."""

from ..context import CapParams, RuleResult, TeamContext, TradeContext

CBA_REF = "2023 CBA Art. VII §6; cbaguide.com/transactions/trades/tpe"


def max_incoming_below_first_apron(outgoing: float, params: CapParams) -> float:
    """Expanded TPE ("greater of" bands, so no discontinuities)."""
    candidates = [1.25 * outgoing + params.allowance]
    if outgoing <= params.tpe_band1_max:
        candidates.append(2.0 * outgoing + params.allowance)
    if outgoing <= params.tpe_band2_max:
        candidates.append(outgoing + params.tpe_band2_add)
    return max(candidates)


def max_incoming_at_or_above_first_apron(outgoing: float, params: CapParams) -> float:
    """Standard TPE only: 100% of outgoing + allowance."""
    return outgoing + params.allowance


class SalaryDataAvailabilityRule:
    code = "SALARY_DATA_AVAILABLE"
    description = "Contract data must be present for all traded players to verify salary rules"

    def evaluate(self, context: TradeContext) -> list[RuleResult]:
        results = []
        for team in context.teams:
            missing = [p.name for p in team.outgoing + team.incoming if p.salary is None]
            if missing:
                provider_note = (
                    "no contract provider is configured"
                    if not context.contract_provider_configured
                    else "the configured provider lacks these players"
                )
                results.append(
                    RuleResult(
                        rule_code=self.code,
                        status="unavailable",
                        team_id=team.team_id,
                        message=(
                            f"Contract data unavailable for {', '.join(missing)} ({provider_note}). "
                            "Salary matching cannot be verified."
                        ),
                        calculation={"missing_players": missing},
                        source_reference=CBA_REF,
                        confidence="high",
                    )
                )
            else:
                results.append(
                    RuleResult(
                        rule_code=self.code,
                        status="pass",
                        team_id=team.team_id,
                        message="Contract data present for all traded players.",
                        source_reference=CBA_REF,
                    )
                )
        return results


class SalaryMatchingRule:
    code = "SALARY_MATCHING"
    description = "Incoming salary must fit the traded player exception for the team's apron status"

    def _team_result(self, team: TeamContext, context: TradeContext) -> RuleResult:
        params = context.params
        outgoing = team.outgoing_salary
        incoming = team.incoming_salary
        if outgoing is None or incoming is None or team.payroll_before is None:
            return RuleResult(
                rule_code=self.code,
                status="unavailable",
                team_id=team.team_id,
                message="Salary matching not evaluated: contract data incomplete for this team.",
                source_reference=CBA_REF,
            )
        if incoming == 0:
            return RuleResult(
                rule_code=self.code,
                status="pass",
                team_id=team.team_id,
                message="No incoming salary; matching not required.",
                calculation={"outgoing_salary": outgoing, "incoming_salary": 0},
                source_reference=CBA_REF,
            )
        if outgoing == 0 and incoming > 0:
            # Taking in salary with none outgoing requires cap room, which needs full
            # league-wide contract data to verify precisely; we check against the cap.
            payroll_after = team.payroll_before + incoming
            fits_cap = payroll_after <= params.salary_cap
            return RuleResult(
                rule_code=self.code,
                status="pass" if fits_cap else "fail",
                team_id=team.team_id,
                message=(
                    "Absorbing salary without sending any out "
                    + ("fits under the salary cap." if fits_cap else "exceeds cap room.")
                ),
                calculation={
                    "incoming_salary": incoming,
                    "payroll_after": payroll_after,
                    "salary_cap": params.salary_cap,
                },
                source_reference=CBA_REF,
                confidence="medium",
            )

        payroll_after = team.payroll_after or 0
        status_after = team.apron_status(payroll_after, params)
        if status_after in ("above_first_apron", "above_second_apron"):
            maximum = max_incoming_at_or_above_first_apron(outgoing, params)
            band = "standard TPE (at/above first apron): 100% of outgoing + $250K"
        else:
            maximum = max_incoming_below_first_apron(outgoing, params)
            band = "expanded TPE (below first apron)"
        ok = incoming <= maximum
        return RuleResult(
            rule_code=self.code,
            status="pass" if ok else "fail",
            team_id=team.team_id,
            message=(
                f"Incoming ${incoming:,.0f} vs maximum ${maximum:,.0f} ({band})."
                + ("" if ok else " Trade fails salary matching.")
            ),
            calculation={
                "outgoing_salary": outgoing,
                "incoming_salary": incoming,
                "maximum_incoming": round(maximum),
                "post_trade_payroll": payroll_after,
                "post_trade_apron_status": status_after,
                "band": band,
            },
            source_reference=CBA_REF,
        )

    def evaluate(self, context: TradeContext) -> list[RuleResult]:
        return [self._team_result(team, context) for team in context.teams]


class SecondApronAggregationRule:
    code = "SECOND_APRON_AGGREGATION"
    description = "Teams above the second apron may not aggregate multiple salaries in one trade"

    def evaluate(self, context: TradeContext) -> list[RuleResult]:
        results = []
        for team in context.teams:
            if not team.aggregates_salaries:
                results.append(
                    RuleResult(
                        rule_code=self.code,
                        status="pass",
                        team_id=team.team_id,
                        message="No salary aggregation in this deal.",
                        source_reference=CBA_REF,
                    )
                )
                continue
            payroll_after = team.payroll_after
            if payroll_after is None:
                results.append(
                    RuleResult(
                        rule_code=self.code,
                        status="unavailable",
                        team_id=team.team_id,
                        message=(
                            "Team aggregates multiple salaries, but apron status cannot be "
                            "determined without contract data."
                        ),
                        source_reference=CBA_REF,
                    )
                )
                continue
            above_second = payroll_after > context.params.second_apron
            results.append(
                RuleResult(
                    rule_code=self.code,
                    status="fail" if above_second else "pass",
                    team_id=team.team_id,
                    message=(
                        "Second-apron team aggregates multiple salaries — prohibited."
                        if above_second
                        else "Aggregation permitted below the second apron."
                    ),
                    calculation={
                        "post_trade_payroll": payroll_after,
                        "second_apron": context.params.second_apron,
                        "outgoing_players": len(team.outgoing),
                    },
                    source_reference=CBA_REF,
                )
            )
        return results


class MinimumTeamSalaryRule:
    code = "MINIMUM_TEAM_SALARY"
    description = "Post-trade payroll below 90% of the cap triggers a warning (not illegal mid-season)"

    def evaluate(self, context: TradeContext) -> list[RuleResult]:
        results = []
        for team in context.teams:
            payroll_after = team.payroll_after
            if payroll_after is None:
                continue  # covered by SALARY_DATA_AVAILABLE
            below = payroll_after < context.params.minimum_team_salary
            results.append(
                RuleResult(
                    rule_code=self.code,
                    status="warning" if below else "pass",
                    team_id=team.team_id,
                    message=(
                        f"Post-trade payroll ${payroll_after:,.0f} is below the minimum team "
                        f"salary ${context.params.minimum_team_salary:,.0f} — shortfall is owed "
                        "to players at season end."
                        if below
                        else "Post-trade payroll meets the minimum team salary."
                    ),
                    calculation={
                        "post_trade_payroll": payroll_after,
                        "minimum_team_salary": context.params.minimum_team_salary,
                    },
                    source_reference="2023 CBA Art. VII §2(b)",
                )
            )
        return results
