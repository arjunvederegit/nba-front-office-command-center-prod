"""Deterministic executive report generation.

The report is a Markdown template filled from computed metrics — every number comes
from the evaluation/legality engines. Optional LLM enhancement (when an API key is
configured) may only rewrite prose sections; it never calculates values or adds
facts, and the deterministic version is always stored alongside."""

from datetime import UTC, datetime

import markdown as md_lib

from app.config import get_settings


def _fmt_money(value: int | None) -> str:
    return f"${value:,.0f}" if value is not None else "unavailable"


def _fmt_score(value: float | None) -> str:
    return f"{value:.0f}/100" if value is not None else "unavailable"


LEGALITY_LABELS = {
    "verified_legal": "Verified legal (all implemented rules passed with current data)",
    "verified_illegal": "Verified illegal (at least one implemented rule failed)",
    "conditionally_valid": "Conditionally valid (implemented rules passed; some required data unavailable)",
    "not_evaluated": "Not evaluated (insufficient data)",
}


def build_report_markdown(
    trade_name: str,
    focal_team_name: str,
    strategy: str,
    legality: dict,
    evaluations: dict[str, dict],
    focal_team_id: str,
    alternatives: list[dict] | None = None,
    data_freshness: dict | None = None,
) -> str:
    settings = get_settings()
    focal = evaluations.get(focal_team_id, {})
    components = focal.get("components", {})
    uncertainty = focal.get("uncertainty", {})
    drivers = sorted(
        ({"k": k, "v": v} for k, v in components.items() if v is not None),
        key=lambda d: abs(d["v"] - 50),
        reverse=True,
    )
    utility = focal.get("composite_utility")
    status = legality.get("overall_status", "not_evaluated")
    perf = focal.get("detail", {}).get("performance", {})
    excluded = focal.get("excluded_components", [])
    suppression = focal.get("suppression") or {}
    decision_status = focal.get("decision_status", "scored")

    if decision_status == "suppressed_illegal":
        verdict = "Do not proceed — the trade fails implemented CBA rules"
    elif utility is None:
        verdict = "No recommendation — this deal could not be scored"
    elif utility >= 55:
        verdict = "Proceed with further diligence"
    elif utility >= 45:
        verdict = "Neutral — depends on strategic priorities"
    else:
        verdict = "Do not proceed as constructed"

    lines: list[str] = []
    lines.append(f"# Executive Trade Recommendation: {trade_name}")
    lines.append("")
    lines.append(
        f"*Prepared for {focal_team_name} · strategy: {strategy} · "
        f"generated {datetime.now(UTC).strftime('%B %d, %Y %H:%M UTC')}*"
    )
    lines.append("")
    lines.append("## 1. Recommendation")
    lines.append("")
    if decision_status == "suppressed_illegal":
        lines.append(f"**{verdict}.**")
        lines.append("")
        lines.append(
            "No composite utility is reported: a deal that fails a verified rule cannot "
            "be executed, so scoring it would invite comparing it against deals that can."
        )
        lines.append("")
        for rule in suppression.get("failing_rules", [])[:6]:
            lines.append(f"- **{rule['rule_code']}** — {rule['message']}")
        lines.append("")
    else:
        lines.append(
            f"**{verdict}.** Composite utility for {focal_team_name}: "
            f"**{_fmt_score(utility)}** (confidence: {focal.get('confidence', 'unknown')})."
        )
        lines.append("")
    lines.append(f"Legality: **{LEGALITY_LABELS.get(status, status)}**")
    lines.append("")

    lines.append("## 2. Strategic rationale")
    lines.append("")
    if decision_status == "suppressed_illegal":
        lines.append(
            "- Component scores are withheld while the deal is illegal. Resolve the rule "
            "failures above and re-evaluate."
        )
    elif not drivers:
        lines.append("- No component could be scored with the data currently available.")
    for d in drivers[:3]:
        direction = "strengthens" if d["v"] >= 50 else "weakens"
        lines.append(f"- The deal {direction} the **{d['k']}** dimension ({_fmt_score(d['v'])}).")
    lines.append("")

    lines.append("## 3. Basketball impact")
    lines.append("")
    if perf.get("delta_wins") is not None:
        lines.append(
            f"- Projected regular-season impact: **{perf['delta_wins']:+.1f} wins** "
            f"(net-rating change {perf.get('delta_net_rating', 0):+.2f}, converted at "
            f"{perf.get('wins_mapping', {}).get('slope', 0):.2f} wins per point, calibrated on "
            f"{perf.get('wins_mapping', {}).get('n', '?')} team-seasons)."
        )
    if uncertainty.get("prob_positive") is not None:
        lines.append(
            f"- Uncertainty (Monte Carlo, {uncertainty.get('n_draws', 0)} draws): median "
            f"{uncertainty.get('median', 0):+.1f} wins, 10th–90th percentile "
            f"[{uncertainty.get('p10', 0):+.1f}, {uncertainty.get('p90', 0):+.1f}], "
            f"P(positive) = {uncertainty['prob_positive']:.0%}."
        )
    elif uncertainty.get("unavailable"):
        lines.append(f"- Uncertainty: not applicable — {uncertainty['unavailable']}.")

    def _named(players: list[dict]) -> str:
        # A player with no impact estimate is named without a fabricated TEI.
        return (
            ", ".join(
                f"{p['name']} (TEI {p['tei']:+.1f})"
                if p.get("tei") is not None
                else f"{p['name']} (impact not modelled)"
                for p in players
            )
            or "none"
        )

    incoming = _named(focal.get("incoming", []))
    outgoing = _named(focal.get("outgoing", []))
    lines.append(f"- Incoming: {incoming}")
    lines.append(f"- Outgoing: {outgoing}")
    lines.append("")

    lines.append("## 4. Financial impact")
    lines.append("")
    team_legality = focal.get("legality", {})
    if team_legality.get("payroll_after") is not None:
        lines.append(
            f"- Post-trade payroll: {_fmt_money(team_legality['payroll_after'])} "
            f"(apron status: {team_legality.get('apron_status_after', 'unknown')})."
        )
        lines.append(
            f"- Salary in: {_fmt_money(team_legality.get('incoming_salary'))}; "
            f"salary out: {_fmt_money(team_legality.get('outgoing_salary'))}."
        )
    else:
        lines.append(
            "- **Contract data unavailable from the configured provider.** Payroll, tax and "
            "apron consequences cannot be verified, and the contract-value component was "
            "excluded from the composite (weights renormalized)."
        )
    lines.append("")

    lines.append("## 5. Key risks")
    lines.append("")
    if uncertainty.get("prob_positive") is not None:
        lines.append(
            f"- {1 - uncertainty['prob_positive']:.0%} of simulations produce a negative win impact."
        )
    risk_detail = focal.get("detail", {}).get("risk", {})
    if risk_detail.get("incoming_availability") is not None:
        lines.append(
            f"- Historical availability of incoming players: "
            f"{risk_detail['incoming_availability']:.0%} of team games "
            "(availability is historical games played, not a medical prediction)."
        )
    # The scored quantity is the CHANGE in exposure, so the report states the change —
    # a level on one side alone was the shape QA-8 filled with a fabricated 85 %.
    if risk_detail.get("availability_delta") is not None:
        delta = risk_detail["availability_delta"]
        direction = "sheds" if delta > 0 else "takes on"
        lines.append(
            f"- Availability exposure: the deal {direction} {abs(delta):.1%} of games "
            "on the minutes involved (minutes-weighted, arriving minus departing). This "
            "is the entire risk component; the projection's own uncertainty is reported "
            "in §3 and deliberately not scored a second time."
        )
    verification = risk_detail.get("legality_verification") or {}
    if verification.get("share") is not None:
        lines.append(
            f"- {verification['rules_with_a_definite_verdict']} of "
            f"{verification['rules_evaluated']} implemented CBA checks reached a verdict "
            "for this team. Reported, never scored."
        )
    warnings = [r for r in legality.get("rule_results", []) if r.get("status") == "warning"]
    for w in warnings[:4]:
        lines.append(f"- Rule warning ({w['rule_code']}): {w['message']}")
    lines.append("")

    lines.append("## 6. Assumptions")
    lines.append("")
    lines.append(
        "- Player impact uses TradeLab Estimated Impact (TEI), a portfolio-model estimate "
        "with documented validation — not a proprietary metric."
    )
    lines.append(
        "- Post-trade minutes are reallocated by the rotation model; a coach's actual "
        "rotation will differ."
    )
    if excluded:
        lines.append(f"- Components excluded for missing data: {', '.join(excluded)}.")
    lines.append("")

    lines.append("## 7. Alternatives considered")
    lines.append("")
    if alternatives:
        for alt in alternatives[:5]:
            lines.append(
                f"- **{alt['name']}** — utility {_fmt_score(alt.get('composite_utility'))}, "
                f"legality: {alt.get('legality_status', 'unknown')}"
            )
    else:
        lines.append(
            "- No saved alternatives in this comparison. Use the comparison view to add 2–5."
        )
    lines.append("")

    lines.append("## 8. Implementation questions")
    lines.append("")
    lines.append(
        "- Are the incoming players' medicals acceptable? (This tool does not model injuries.)"
    )
    lines.append(
        "- Does the locker-room / role fit survive contact with the coaching staff's plans?"
    )
    if status == "conditionally_valid":
        lines.append(
            "- Verify salary matching with authoritative contract data before any commitment."
        )
    lines.append("")

    lines.append("## 9. Data freshness and limitations")
    lines.append("")
    freshness = data_freshness or {}
    lines.append(
        f"- Source: NBA.com via `nba_api` · rosters/stats last synced: "
        f"{freshness.get('last_sync', 'unknown')} · season {settings.current_season}."
    )
    lines.append(
        f"- Cap parameters: {legality.get('cap_parameters_source', 'unknown')} "
        f"(league year {legality.get('league_year')})."
    )
    lines.append(
        "- This is an analytical portfolio project, not an official NBA cap-management "
        "product; legality coverage is a documented subset of the CBA "
        "(see docs/cba-rule-coverage.md)."
    )
    lines.append("")
    return "\n".join(lines)


def report_to_html(markdown_text: str) -> str:
    body = md_lib.markdown(markdown_text, extensions=["tables"])
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>TradeLab Executive Report</title>
<style>
body {{ font-family: Georgia, serif; max-width: 760px; margin: 40px auto; padding: 0 20px; color: #1a1a2e; }}
h1 {{ font-size: 1.6rem; border-bottom: 2px solid #1a1a2e; padding-bottom: 8px; }}
h2 {{ font-size: 1.1rem; margin-top: 28px; }}
li {{ margin: 4px 0; }}
em {{ color: #555; }}
@media print {{ body {{ margin: 12px; }} }}
</style></head><body>{body}</body></html>"""
