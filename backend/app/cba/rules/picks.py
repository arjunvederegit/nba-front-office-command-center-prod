"""Draft-pick rules.

Without an authoritative pick-ownership provider the Stepien rule cannot be
certified; hypothetical picks are allowed in construction but clearly labeled and the
rule reports `unavailable` instead of a fake verdict."""

from ..context import RuleResult, TradeContext


class StepienRule:
    code = "STEPIEN_FUTURE_FIRSTS"
    description = (
        "Teams may not leave themselves without first-round picks in consecutive future drafts"
    )

    def evaluate(self, context: TradeContext) -> list[RuleResult]:
        results = []
        for team in context.teams:
            firsts_out = [p for p in team.picks_out if p.round_number == 1]
            if not firsts_out:
                continue
            hypothetical = [p for p in firsts_out if p.is_hypothetical]
            if hypothetical:
                results.append(
                    RuleResult(
                        rule_code=self.code,
                        status="unavailable",
                        team_id=team.team_id,
                        message=(
                            f"{len(firsts_out)} outgoing first-round pick(s) are hypothetical — no "
                            "authoritative pick-ownership provider is configured, so Stepien-rule "
                            "compliance cannot be certified."
                        ),
                        calculation={
                            "outgoing_firsts": [
                                {"year": p.draft_year, "protections": p.protections}
                                for p in firsts_out
                            ]
                        },
                        source_reference="NBA Stepien rule (consecutive future firsts)",
                        confidence="low",
                    )
                )
        return results
