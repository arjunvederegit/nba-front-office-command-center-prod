"""Roster fit: do incoming players address team needs without harmful redundancy?

    F = sum_k( n_k * delta_s_k ) - gamma * sum_k( max(0, r_k) )

- n_k: severity of need k (0..1, from transparent percentile rules)
- delta_s_k: minutes-weighted change in skill k from the trade (incoming - outgoing)
- r_k: redundancy — skill added where the roster is already strong

Skill vectors are percentiles of the scored league population, so a +0.3 change in a
skill means adding a player materially better than the roster is losing."""

GAMMA = 0.35


def fit_score(
    needs: dict[str, float],
    incoming: list[tuple[dict[str, float], float]],
    outgoing: list[tuple[dict[str, float], float]],
    roster_strengths: dict[str, float],
    need_to_skill: dict[str, str],
) -> tuple[float, dict]:
    """incoming/outgoing: [(skill_vector, minutes_weight)]; minutes weights normalize
    so one 30-minute player counts more than two 8-minute players.
    roster_strengths: skill percentile of the current roster's top rotation (0..1).
    Returns (raw fit score, explanation detail)."""

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
    all_keys = set(skills_in) | set(skills_out)
    delta = {k: skills_in.get(k, 0.5) - skills_out.get(k, 0.5) for k in all_keys}

    needs_term = 0.0
    contributions: dict[str, float] = {}
    for need_key, severity in needs.items():
        skill_key = need_to_skill.get(need_key)
        if skill_key is None or skill_key not in delta:
            continue
        contribution = severity * delta[skill_key]
        needs_term += contribution
        contributions[need_key] = round(contribution, 4)

    redundancy_term = 0.0
    redundancies: dict[str, float] = {}
    for skill_key, change in delta.items():
        strength = roster_strengths.get(skill_key, 0.5)
        # Adding to an already-strong skill (>70th percentile) is redundant in
        # proportion to how strong the roster already is there.
        if change > 0 and strength > 0.7:
            redundancy = change * (strength - 0.7) / 0.3
            redundancy_term += redundancy
            redundancies[skill_key] = round(redundancy, 4)

    score = needs_term - GAMMA * redundancy_term
    return score, {
        "needs_addressed": contributions,
        "redundancies": redundancies,
        "skill_delta": {k: round(v, 4) for k, v in delta.items()},
        "gamma": GAMMA,
    }
