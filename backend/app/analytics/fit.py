"""Roster fit: do incoming players address team needs without harmful redundancy?

    F = sum_k( n_k * delta_s_k ) - gamma * sum_k( max(0, r_k) )

- n_k: severity of need k (0..1, from transparent percentile rules)
- delta_s_k: minutes-weighted change in skill k from the trade (incoming - outgoing)
- r_k: redundancy — skill added where the roster is already strong

**The sum runs over SKILLS, not over needs (R4-1a).** Several needs legitimately point at
one skill — `playmaking` and `secondary_creation` are both creation problems — and the
previous loop ran over needs, so one skill delta was multiplied by two or three severities
and added that many times. Measured on the 30 seeded teams before the fix: 19 of 30 had at
least one skill claimed by two or more active needs, and the inflation (sum of severities
over the largest single severity) averaged **1.625x**, peaking at **2.67x** where
`playmaking`, `ball_security` and `secondary_creation` all resolved to `creation`.

A skill's severity is the **maximum** over the needs that map to it, not the sum. Two
independent signals that a roster cannot create shots do not make the need twice as
severe, and severity is defined on 0..1 — summing leaves that range and silently
reintroduces the double count that this fix exists to remove.

Skill vectors are percentiles of the scored league population, so a +0.3 change in a
skill means adding a player materially better than the roster is losing."""

GAMMA = 0.35


def fit_score(
    needs: dict[str, float],
    incoming: list[tuple[dict[str, float], float]],
    outgoing: list[tuple[dict[str, float], float]],
    roster_strengths: dict[str, float | None],
    need_to_skill: dict[str, str],
) -> tuple[float, dict]:
    """incoming/outgoing: [(skill_vector, minutes_weight)]; minutes weights normalize
    so one 30-minute player counts more than two 8-minute players.
    roster_strengths: skill percentile of the current roster's top rotation (0..1), or
    None where fewer than three rotation players have that skill measured.
    Returns (raw fit score, explanation detail).

    **A skill only enters the delta when both sides measure it.** Previously a skill
    present on one side and absent on the other was compared against a hardcoded 0.5,
    which is the 50th percentile of the league — a fabricated median player standing in
    for a measurement that does not exist. Skills measured on only one side are reported
    under `skills_not_compared` instead of being scored.
    """

    def weighted_skills(entries: list[tuple[dict[str, float], float]]) -> dict[str, float]:
        total_weight = sum(w for _, w in entries)
        if total_weight <= 0:
            return {}
        out: dict[str, float] = {}
        for skills, weight in entries:
            for key, value in skills.items():
                out[key] = out.get(key, 0.0) + value * (weight / total_weight)
        return out

    skills_in = weighted_skills(incoming)
    skills_out = weighted_skills(outgoing)
    comparable = set(skills_in) & set(skills_out)
    not_compared = sorted((set(skills_in) | set(skills_out)) - comparable)
    delta = {k: skills_in[k] - skills_out[k] for k in comparable}

    # Group the needs by the skill that addresses them, so each skill delta is scored
    # exactly once (R4-1a).
    needs_by_skill: dict[str, list[tuple[str, float]]] = {}
    for need_key, severity in needs.items():
        skill_key = need_to_skill.get(need_key)
        if skill_key is None or skill_key not in delta:
            continue
        needs_by_skill.setdefault(skill_key, []).append((need_key, severity))

    needs_term = 0.0
    contributions: dict[str, float] = {}
    skill_severities: dict[str, float] = {}
    shared_skills: dict[str, list[str]] = {}
    for skill_key, entries in needs_by_skill.items():
        severity = max(s for _, s in entries)
        contribution = severity * delta[skill_key]
        needs_term += contribution
        skill_severities[skill_key] = round(severity, 4)
        if len(entries) > 1:
            shared_skills[skill_key] = sorted(k for k, _ in entries)
        # The UI lists contributions per NEED, so the skill's single contribution is
        # split across the needs that claimed it, in proportion to their severities.
        # The parts sum to the skill's contribution — never to a multiple of it.
        total = sum(s for _, s in entries)
        for need_key, need_severity in entries:
            share = (need_severity / total) if total > 0 else 1.0 / len(entries)
            contributions[need_key] = round(contribution * share, 4)

    redundancy_term = 0.0
    redundancies: dict[str, float] = {}
    for skill_key, change in delta.items():
        strength = roster_strengths.get(skill_key)
        # Adding to an already-strong skill (>70th percentile) is redundant in
        # proportion to how strong the roster already is there. An unmeasured strength
        # cannot establish redundancy, so it contributes nothing rather than 0.5.
        if strength is not None and change > 0 and strength > 0.7:
            redundancy = change * (strength - 0.7) / 0.3
            redundancy_term += redundancy
            redundancies[skill_key] = round(redundancy, 4)

    score = needs_term - GAMMA * redundancy_term
    return score, {
        "needs_addressed": contributions,
        "redundancies": redundancies,
        "skill_delta": {k: round(v, 4) for k, v in delta.items()},
        "skills_not_compared": not_compared,
        # Severity actually applied per skill (the max over its needs), and which needs
        # shared one skill. Both are disclosed so the per-need numbers above can be
        # reconciled with the score rather than looking arbitrarily deflated.
        "skill_severity_applied": skill_severities,
        "needs_sharing_a_skill": shared_skills,
        "gamma": GAMMA,
    }
