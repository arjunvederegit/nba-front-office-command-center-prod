"""Draft-pick rules.

Until R5 the Stepien rule had no ownership source and could only ever report
`unavailable`. It now certifies the teams a reconciled source resolves and keeps
reporting `unavailable` — **naming the specific unresolved clause** — for the rest.

That split is the whole point. Roughly half the traded picks in the RealGM snapshot are
swaps, protections or conditional conveyances that cannot be reduced to an owner, so a
verdict for those teams would be a fabrication. The other half can be certified, and
withholding a verdict there would be its own dishonesty.
"""

from ..context import RuleResult, TeamContext, TradeContext

SOURCE = "NBA Stepien rule (consecutive future firsts)"


def _post_trade_holdings(team: TeamContext) -> dict[int, int]:
    holdings = dict(team.first_round_holdings or {})
    for pick in team.picks_out:
        if pick.round_number == 1:
            holdings[pick.draft_year] = holdings.get(pick.draft_year, 0) - 1
    for pick in team.picks_in:
        if pick.round_number == 1:
            holdings[pick.draft_year] = holdings.get(pick.draft_year, 0) + 1
    return holdings


def _consecutive_gaps(holdings: dict[int, int]) -> list[tuple[int, int]]:
    """Year pairs where the team holds no first in either draft."""
    years = sorted(holdings)
    return [
        (a, b)
        for a, b in zip(years[:-1], years[1:], strict=False)
        if b == a + 1 and holdings[a] <= 0 and holdings[b] <= 0
    ]


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
            outgoing = [
                {"year": p.draft_year, "protections": p.protections} for p in firsts_out
            ]

            if team.first_round_holdings is None:
                unresolved = team.pick_ownership_unresolved
                reason = (
                    "no authoritative pick-ownership provider is configured"
                    if not unresolved
                    else (
                        f"{len(unresolved)} of this team's pick entries are swaps, "
                        "protected picks or conditional conveyances that no source "
                        "reduces to an owner"
                    )
                )
                results.append(
                    RuleResult(
                        rule_code=self.code,
                        status="unavailable",
                        team_id=team.team_id,
                        message=(
                            f"{len(firsts_out)} outgoing first-round pick(s), and "
                            f"{reason} — Stepien-rule compliance cannot be certified."
                        ),
                        calculation={
                            "outgoing_firsts": outgoing,
                            "unresolved_ownership": unresolved[:6],
                            "unresolved_total": len(unresolved),
                        },
                        source_reference=SOURCE,
                        confidence="low",
                    )
                )
                continue

            holdings = _post_trade_holdings(team)
            # A pick the team does not verifiably hold cannot be checked against a rule
            # about what it retains. Report rather than assume in either direction.
            phantom = [
                p.draft_year
                for p in firsts_out
                if (team.first_round_holdings or {}).get(p.draft_year, 0) <= 0
            ]
            if phantom:
                results.append(
                    RuleResult(
                        rule_code=self.code,
                        status="unavailable",
                        team_id=team.team_id,
                        message=(
                            "this trade sends away first-round pick(s) for "
                            + ", ".join(str(y) for y in sorted(set(phantom)))
                            + " that the reconciled ownership source does not show this "
                            "team holding — the construction and the source disagree, so "
                            "no verdict is reported."
                        ),
                        calculation={
                            "outgoing_firsts": outgoing,
                            "holdings_before": team.first_round_holdings,
                        },
                        source_reference=SOURCE,
                        confidence="low",
                    )
                )
                continue

            gaps = _consecutive_gaps(holdings)
            results.append(
                RuleResult(
                    rule_code=self.code,
                    status="fail" if gaps else "pass",
                    team_id=team.team_id,
                    message=(
                        "leaves the team without a first-round pick in "
                        + " and ".join(f"{a} and {b}" for a, b in gaps)
                        + " — consecutive future drafts."
                        if gaps
                        else "the team retains a first-round pick in every pair of "
                        "consecutive future drafts the ownership source covers."
                    ),
                    calculation={
                        "outgoing_firsts": outgoing,
                        "holdings_before": team.first_round_holdings,
                        "holdings_after": holdings,
                        "consecutive_gaps": [list(g) for g in gaps],
                        "years_covered": sorted(holdings),
                    },
                    source_reference=SOURCE,
                    confidence="high",
                )
            )
        return results
