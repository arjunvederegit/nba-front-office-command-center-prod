# Demo script (~7 minutes)

Rewritten in R7 against the shipped product. Every route, control and phrase below was
walked in a browser at the R7 commit; where a number is quoted it came from the live
application, not from a plan.

**Prep**

```bash
make migrate
make sync-data                                  # NBA.com, ~1 min
make sync-corpus-stats                          # ten seasons + season calendars
make import-stats-csv                           # the season-totals directory
make import-draft-picks                         # 92 verified picks, 103 unresolved
make fetch-transactions FROM=2017 TO=2026        # ~40 s, honours Crawl-delay 3
make import-transactions                        # 565 trades
make train && make score
make dev                                        # backend :8000, frontend :3000
```

Contracts are deliberately **not** configured for this walkthrough. The honest-unavailable
behaviour is the point of section 6, and it cannot be shown on a database that has them.
If you want the partial-coverage version too, `rosterlab-qa.db` and the
`backend-partial-contracts` launch configuration exist for it.

Have `/` open.

---

## 1 · Frame the problem (40 s)

> "Should we make this trade?" is not one question. On-court value, cap law, roster fit,
> timeline, risk and optionality pull in different directions, and which of them wins
> depends on the strategy you have chosen. RosterLab keeps the question in pieces instead
> of collapsing it to a number.

Point at the header badges: **2025-26 season**, and the freshness pill — it reads
**Data aging**, not "live", because the last NBA.com retrieval is over a day old. The
product states what it does not know before you ask it anything.

## 2 · Team Outlook — where a decision starts (75 s)

**Team Outlook → Boston Celtics.**

- **Window: Closing**, with the reason underneath — a veteran rotation.
- **Strengths & needs** come from percentile rules over real league stats. Boston is 97th
  in overall offense and **0th in playmaking**.
- Note the second need: **"Point-of-attack defense · no skill addresses this."** R4 built a
  point-of-attack composite, measured it against the metric it was replacing, found it
  **worse** — 0.630 against 0.611 on its own pre-registered class — and withdrew the claim
  rather than restating it. The team-side need is still measured and still shown; what is
  gone is the pretence that a player skill answers it.

**Who fixes this?** — the need-driven acquisition panel.

- Both rules are printed above the list: the **filter** (only players whose creation
  percentile exceeds this roster's own, 80 %) and the **ranking** (projected win change
  from adding the player). Cost is reported beside each name and never folded into the
  order.
- The accounting line at the bottom is the honest part: *514 players considered · 377 do
  not improve this need · 40 have the skill unmeasured · 42 trades evaluated against a
  budget of 60*, then the rejection reasons. Every candidate shown has already been run
  through the trade evaluator for **both** teams.

## 3 · Trade Evaluator — build it (60 s)

**Start a trade** from Boston. Add **New York**. Send **Jaylen Brown** one way and
**OG Anunoby** the other — drag, or use the labelled send button on any roster card.

The header badges update live: **Cap year 2026-27**, **2/2 teams · 2 players moving**, and
the rules check runs on the backend the moment an asset crosses the lane. It reports
**Incomplete check — data missing**, which is the correct verdict with no contract
provider configured: salary matching cannot be evaluated, so the deal is never called
legal.

**Evaluate this deal.**

## 4 · Read the verdict (90 s)

- **Clear loss for BOS, decision score 31**, confidence medium.
- Immediately underneath: *"Not scored because the data is missing: Contract value,
  Flexibility & future value — the remaining weights were rescaled so the score stays
  comparable."* And: *"3 players have no impact estimate and were left out of the
  projection rather than given a league-average stand-in"*, naming them. They still count
  against the roster limits.
- **Projected wins impact** is a band, not a point: median −4.6 wins, 10th–90th −8.3 to
  −0.8, **6 % chance it helps**, over 2,000 simulations. Say the line on screen out loud —
  *the band is the honest answer; the midpoint alone would overstate what the model knows.*
- **Component scores** — four scored, two explicitly not, each with a one-line definition.

## 5 · Precedent — evidence, not model output (75 s)

The **Precedent** tab. This is the feature that answers a question the model cannot.

> These are the completed trades yours most resembles. Not trades the model likes — trades
> that happened.

For Brown-for-Anunoby it returns Nurkić-for-Sexton, Caruso-for-Giddey,
Rozier-for-Walker and George-for-Oladipo-and-Sabonis: star-adjacent wings and guards
swapped one-for-one. Four of the five come from seasons the corpus could not rank before
R7 widened it.

Three things to point at:

- **Ranked over 1,151 team-sides of 535 completed trades**, and the coverage rail names the
  30 ingested trades that still cannot be ranked at all.
- The retrieval unit is a **side**, not a trade — sending a star for picks and receiving one
  are different decisions, and at most one side of any trade appears in a list.
- **"Resemblance is not consequence."** Nothing here reads what happened next. A historical
  deal that worked is not an argument that this one will, and the panel says so rather than
  leaving it implied.

Also on this screen: **Rotation consequences** — what the deal does to minutes by role, out
of 240. Roster composition, explicitly *not* lineup data. R6 measured whether five-man
lineup data could support a fit model, found a median of 20.2 minutes per five-man group
and an implied ±16 net-rating standard error against a ±10 league spread, and refused to
ship it. `make lineup-availability` re-runs that measurement; the deferral is falsifiable
by design.

## 6 · Data Health — what is missing, in plain language (45 s)

**Data Health.**

- **1 critical source missing.** Contracts & salaries is *not configured*, and the card
  says what that costs: *"Salary matching, apron limits and payroll stay unavailable
  product-wide — no trade will ever be reported as legal from partial checks."*
- Every source carries a **next step** you can paste into a terminal.
- **Completed trades** — 565 trades, 10 season calendars. The calendar is what decides
  which season each trade is described by; without it the feature season falls back to the
  calendar month, and the card reports `incomplete` rather than pretending otherwise.

> Every screen traces to one of these sources. When a source is missing the product says
> so instead of estimating around it.

## 7 · Strategy Lab and the memo (45 s)

**Strategy Lab** with two or more saved deals: drag the priority sliders and the ranking
recomputes from the stored component scores — no re-evaluation, no invented alternative.
Domination is judged on **all six** components and the compared axes are published, so
"A dominates B" means what it says.

From a saved trade, the **decision memo**: the evaluation as a reviewable artifact, ending
in **"What is not known"** — on a live deal that section has eight entries, every one of
which existed before the memo and none of which was collected anywhere.

## Close (20 s)

> Everything here is reproducible from the commands at the top, and every number traces to
> a timestamped retrieval. Where the data does not support a claim, the product says
> unavailable — it never estimates around a gap, and it never reports a trade as legal from
> a partial check.
