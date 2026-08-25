# CBA rule coverage

RosterLab implements a **meaningful, documented subset** of the 2023 NBA–NBPA
Collective Bargaining Agreement's trade rules. This page is the authoritative map of
what is and isn't covered. The engine's honesty standard means anything not listed
as implemented reports `unavailable` or is simply out of scope — **a trade is never
labeled legal from partial validation**.

Legality states: `verified_legal` (all implemented required rules passed with
current data) · `verified_illegal` (≥1 implemented rule failed) ·
`conditionally_valid` (implemented rules passed; required data unavailable) ·
`not_evaluated` (insufficient data).

Primary references: 2023 NBA–NBPA CBA Article VII; [cbaguide.com — Traded Player
Exceptions](https://cbaguide.com/transactions/trades/tpe/); [Hoops Rumors TPE
glossary](https://www.hoopsrumors.com/2024/06/hoops-rumors-glossary-traded-player-exception-5.html);
official NBA cap releases for [2025-26](../backend/app/config/cap_rules/2025-26.yaml)
and [2026-27](../backend/app/config/cap_rules/2026-27.yaml) dollar figures.

---

## SALARY_DATA_AVAILABLE — full

**Plain English:** salary rules can only be verified when every traded player's
salary is known. `nba_api` supplies no contract data, so with no configured contract
provider this reports `unavailable`, capping the overall result at
`conditionally_valid`.
**Tests:** `test_salary_matching.py::TestSalaryMatchingRule::test_unavailable_when_salary_missing`.

## SALARY_MATCHING — partial (core bands)

**Plain English:** a team over the cap must send out salary roughly comparable to
what it takes back; how much more it may receive depends on its post-trade apron
status.
**Formula (below first apron, expanded TPE; 2025-26 anchors scaled by cap ratio per
the CBA):**

```
outgoing ≤ $8.846M              → max_in = 200%·outgoing + $250K
$8.846M < outgoing ≤ $35.384M   → max_in = outgoing + $9.096M
outgoing > $35.384M             → max_in = 125%·outgoing + $250K
```

**At/above first apron (standard TPE):** `max_in = outgoing + $250K`.
**Applies to:** each team's aggregate non-two-way salaries in the deal.
**Edge cases covered:** zero-incoming side (pass), absorbing with no outgoing
(checked against cap room, medium confidence), band-edge continuity (the CBA's
dollar anchors make the formulas exactly continuous — unit-tested).
**Edge cases NOT covered:** salary for TPE purposes vs actual salary (incentives,
poison-pill/BYC, non-guaranteed reductions), pre-existing trade exceptions, minimum
contracts absorbed via minimum exception.
**Confidence:** high on the implemented bands.
**Tests:** `TestMatchingBands` (5 tests), `TestSalaryMatchingRule` (4 tests).

## SECOND_APRON_AGGREGATION — full (for player salaries in one deal)

**Plain English:** a team above the second apron may not combine two or more player
salaries in one trade for matching purposes.
**Implementation:** teams sending ≥2 standard contracts fail when post-trade payroll
exceeds the second apron; `unavailable` when payroll can't be computed.
**Tests:** `TestSecondApronAggregation` (2 tests).

## MINIMUM_TEAM_SALARY — full (as warning)

**Plain English:** payroll below 90% of the cap isn't an illegal trade mid-season,
but the shortfall is owed to players — surfaced as a warning with the exact numbers.
**Tests:** `TestMinimumTeamSalary` (2 tests).

## ROSTER_SIZE — partial (honest two-way ambiguity)

**Plain English:** rosters carry ≤15 standard + 3 two-way players; below 14 standard
is allowed only briefly; 12 is the hard floor. NBA.com roster snapshots include
two-way players without marking them, so **without contract data** only the 18-spot
ceiling and 12 floor are certain violations; 16–18 yields a warning explaining the
ambiguity (medium confidence). With contract types the precise 15-standard check
applies.
**Tests:** `TestRosterSize` (3 tests).

## RECENTLY_SIGNED — partial (requires signing dates)

**Plain English:** most newly signed free agents can't be traded for 3 months or
until Dec 15, whichever is later. Implemented against `signed_date` from the
contract provider; without one the rule stays silent for missing dates (covered by
SALARY_DATA_AVAILABLE) or reports `unavailable` per player when a provider exists
but lacks the date. Special cases (Bird-rights raises >20%, sign-and-trade windows)
are not modeled.
**Confidence:** medium.
**Tests:** `TestRecentlySigned` (2 tests).

## NO_TRADE_CLAUSE — full (warning, data permitting)

**Plain English:** a player with a no-trade clause must consent; the engine warns
rather than blocks (consent is a real-world outcome). Requires provider data.
**Tests:** `TestNoTradeClause`.

## TWO_WAY_EXCLUSION — full (data permitting)

**Plain English:** two-way salaries don't count toward matching. Excluded from
outgoing/incoming totals and noted in results.
**Tests:** `TestTwoWayExclusion`.

## STEPIEN_FUTURE_FIRSTS — unavailable by design

**Plain English:** teams may not leave themselves without first-round picks in
consecutive future drafts. RosterLab has **no authoritative pick-ownership provider**,
picks in trades are user-added hypotheticals (labeled), so the rule reports
`unavailable` with low confidence whenever firsts are traded — compliance is never
certified.

---

## Explicitly unsupported (never silently faked)

Sign-and-trade transactions · existing traded-player exceptions and their use ·
cash considerations · base-year compensation / poison-pill provisions · hard-cap
triggers from exception use · salary guarantee/incentive adjustments to trade salary
· aggregation timing restrictions for recently acquired players (requires
transaction-date data) · draft-pick swap legality.

Each of these fails safe: either the relevant data is absent (→ `unavailable` /
`conditionally_valid`) or the structure can't be expressed in the builder at all.
