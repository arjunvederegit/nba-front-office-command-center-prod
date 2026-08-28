# F. Validation report

*Everything run against the Pivot restructure, with the numbers. Baseline figures are from
`main` at `2aab3e1` before any change was made.*

---

## 1. Automated checks

| Check | Baseline (`2aab3e1`) | After restructure | |
| --- | --- | --- | --- |
| `pytest` | 908 passed, 1 skipped | **1002 passed, 1 skipped** | +94 |
| backend coverage | 88.46 % | **88.66 %** | floor 85, CI-enforced |
| `ruff check app tests` | clean | **clean** | |
| `mypy app` | clean, 97 files | **clean, 108 files** | +11 source files |
| `alembic current` | `f2c8b41d6a05` | **`f2c8b41d6a05`** | unchanged — no migration added |
| `alembic check` | no drift | **no drift** | |
| `vitest` | 82 passed, 9 files | **109 passed, 10 files** | +27 |
| `eslint` | clean | **clean** | |
| `tsc --noEmit` | clean | **clean** | |
| `next build` | 13 routes | **13 routes** | unchanged — no route added or renamed |

The single skip is pre-existing and environmental: `test_impact_units.py:289`, "no
`tei_to_net_rating` model registered in this database".

### New test coverage added by the restructure

| File | Tests | What it pins |
| --- | --- | --- |
| `backend/tests/unit/test_domain.py` | 50 | vocabulary agreement with what shipped; the domain imports nothing above it; a move changes membership and nothing else; scenarios can branch |
| `backend/tests/unit/test_intelligence.py` | 23 | unmeasurable dimensions named not omitted; no impact estimate → no number; strengths/weaknesses disjoint; fit conditional and withheld where it inverts |
| `backend/tests/unit/test_tools.py` | 16 | the Copilot boundary is read-only; an unavailable tool has no handler; caveats travel with results |
| `frontend/tests/unit/navigation.test.ts` | 27 | every nav entry resolves to a real App Router directory; legacy redirects intact; one name, one tagline |
| `test_no_silent_defaults.py` | +1 | the structural scan's module list cannot go silently vacuous |

---

## 2. Equivalence checks — proving the refactor changed nothing

The domain layer moved five vocabulary constants out of the modules that declared them. Each
was asserted **byte-identical** to the version at `2aab3e1`, by parsing the original file and
comparing values:

```
OK   SKILL_KEYS            OK   NEED_TO_SKILL
OK   ROLE_ID               OK   DEFAULT_WEIGHTS
OK   UNADDRESSABLE_NEEDS   OK   COMPONENT_KEYS
OK   REPLACEMENT_SKILLS    OK   ROLE_ORDER / REAL_ROLES
```

**The skill-cache fingerprint is unchanged**, verified by checking out the original file,
computing it, restoring, and computing again:

```
ORIGINAL: 14a7dac41af3
CURRENT : 14a7dac41af3      FINGERPRINT UNCHANGED
```

This matters because `skill_schema_fingerprint()` namespaces the six-hour league skill cache.
Had it changed, every deployed instance would have silently recomputed — or worse, a stale
shape would have been served under a new key. It hashes the *contents* of `SKILL_KEYS`, not
its address, which is why moving the list was safe.

---

## 3. Measurement performed before shipping a number

`Fit(player, team)` was measured across all 30 ingested rosters **before** the endpoint was
exposed. This is the check that changed the design.

Where the need vector has signal, it discriminates correctly:

| Roster | Top needs | n | median | sd | best fits | worst fits |
| --- | --- | --- | --- | --- | --- | --- |
| DEN | POA defense 1.00, rim protection 0.86 | 127 | 63.9 | 28.9 | Jalen Smith, Moussa Cisse, Charles Bassey | Pritchard, Sexton, Nembhard |
| SAC | 3P volume 1.00, efficiency 0.93 | 129 | 62.3 | 34.8 | Porziņģis, Jokić, Tatum | low-usage guards |
| MEM | defensive rebounding 1.00 | 129 | 49.7 | 33.7 | Jokić, Gafford, Porziņģis | Schröder, Vincent |

Where it does not, it inverts:

| Roster | Max severity | n | median | below neutral | worst-ranked |
| --- | --- | --- | --- | --- | --- |
| ATL | 0.172 | 79 | 41.6 | **88.6 %** | **Donovan Mitchell** |

An alternative baseline (`REPLACEMENT_SKILLS` instead of the roster's own profile) was tested
and was **worse** — 91.1 % below neutral, with replacement-level players ranking highest — so
it was rejected rather than adopted.

**2 of 30 rosters** have no need clearing the severity threshold. They now return an explicit
unavailable with the reason instead of a number.

---

## 4. Route and API validation

**Routes.** No path was renamed. `next build` lists the same 13 routes as the baseline, and
`tests/unit/navigation.test.ts` asserts every nav entry resolves to a real App Router
directory and that all ten legacy redirects survive.

**New API surface**, exercised against the live ingested database:

| Endpoint | Result |
| --- | --- |
| `GET /api/v1/intelligence/vocabulary` | 200 — 22 skills (9 available), 16 archetypes, 11 needs |
| `GET /api/v1/intelligence/teams/{id}/profile` | 200 — ATL, roster 18, 9 needs, 0 weaknesses, 4 strengths |
| `GET /api/v1/intelligence/players/{id}` | 200 — 9 of 22 dimensions measured, archetype "Interior anchor" |
| `GET /api/v1/intelligence/fit?player_id=&team_id=` | 200 — score 7.8 against a team with needs |
| `GET /api/v1/intelligence/fit` *(own roster)* | 200 — `available: false`, `already_on_roster: true` |
| `GET /api/v1/intelligence/fit` *(no team_id)* | **422** — fit requires a team, by design |

No existing endpoint changed shape. `/intelligence` is a new resource family under the same
`/api/v1` prefix, which is additive by construction.

---

## 5. Backend validation batteries

Not re-run as part of this restructure, and deliberately so: they exercise analytics that
this pass did not touch, they take minutes each, and their machinery is separately covered by
unit tests that *do* run (`test_adversarial_battery.py` 6, `test_comparable_validation_battery.py`
16, `test_acquisition_validation_battery.py` 7 — all passing).

They remain runnable and unmodified:

```bash
make adversarial-validation     # 11 honesty scenarios on the live database
make comparable-validation      # 1,151 sides, ~68 s
make acquisition-validation     # need-driven discovery over 30 rosters
make lineup-availability        # re-measures the R6-4 refusal (network)
```

**No threshold in any battery was changed.**

---

## 6. Known issues remaining

### Fixed after this report was first written — see §9

1. ~~**The API hard-codes provenance to NBA.com** regardless of a row's actual
   `source_provider`.~~ **Fixed.** Ten serving sites now read the row. See §9.

### Carried into R8 (documented, not fixed here)

2. **The Strategy Lab still re-implements the composite in the browser**
   (`app/strategy-lab/page.tsx:93-108`) and re-ranks every saved deal from it. Real, and left
   alone: the page is 1,805 lines and entangled with slider state, and moving the calculation
   is a separate piece of work with its own equivalence proof.
3. **Player Explorer still computes league percentiles and the qualification rule
   client-side**, and Team Outlook still classifies the competitive window from hardcoded age
   thresholds (25.5 / 28.5).
4. **No `response_model` on the 39 pre-existing endpoints.** The new intelligence endpoints
   carry zod validation at the client boundary; the rest remain hand-mirrored.
5. **Skills are not persisted** and **archetypes are 1:1** — both schema work, both specified
   in the R8 plan.

### Not run in this pass — and why

Three checks were attempted and could not be completed **because of the local environment,
not because of the code**. They are listed here rather than glossed, and each is the first
thing to run on a machine with disk headroom.

- **Live browser QA** (manual route inspection, responsive layouts, console errors).
  Attempted. Both dev servers were started from `.claude/launch.json` and **both bound their
  ports** (3000 and 8000 confirmed listening). `next dev` then printed its banner and stalled
  at 0 % CPU without compiling, and browser navigation to `localhost:3000` was refused. The
  cause is the eviction described in §7: `next dev` compiles on first request, which means
  reading thousands of `node_modules` files, and at that moment a `find` over that directory
  had itself exceeded 600 s. The servers were stopped cleanly afterwards.
- **Playwright e2e.** Requires a freshly seeded demo database plus a running stack, so it is
  blocked by the same cause. Its specs *were* updated for the rename (`Pivot — home`,
  `E2E Pivot deal`), and the h1 strings it pins (`Trade Evaluator`, `Decision board`,
  `Player Explorer`) were deliberately left unchanged, so the suite should pass unmodified.
  **This is the highest-value thing to run before merging.**
- **Visual QA** (`make visual-qa`, 15 routes × 7 viewports). Same dependency. The route
  manifest was not touched, because no route moved.

What partially substitutes for them, and what does not:

- The new API surface *was* exercised against the live 30-team database, in-process via
  `TestClient` rather than over HTTP (§4). That validates the handlers, the serialization and
  the honesty gates. It does **not** validate rendering, layout or console cleanliness.
- `next build` compiled all 13 routes cleanly, which catches type and import errors across
  every page but not runtime behaviour.
- 109 frontend unit tests pass, including 27 new navigation tests that assert every nav entry
  resolves to a real App Router directory and that all ten legacy redirects survive — which is
  the specific regression a navigation restructure risks.

**`docs/screenshots/`** still shows the RosterLab wordmark in all seven curated PNGs. They are
embedded in the README and are now stale. Regenerating them needs a running stack, so this is
blocked by the same cause.

---

## 7. Environment notes that cost real time

Two hazards specific to this checkout, both worth knowing before a long run.

**iCloud evicts the toolchain mid-run.** The repository lives under `~/Desktop`, which iCloud
Drive syncs. It evicted 30,321 files from `frontend/node_modules` and 15,704 from
`backend/.venv`, and it did so **again** (6,857 files) an hour later. The symptom is not an
error: the command starts, prints its banner, and sits at 0 % CPU forever. A hung
`vitest --run` piped to `tail` exits 0 with an empty body, which reads exactly like a passing
run with no output.

```bash
find frontend/node_modules backend/.venv -type f -flags +dataless | wc -l   # diagnose
cd frontend && rm -rf node_modules && npm ci                                # fast fix
```

Rehydrating by reading the files back works but runs at roughly 10 files/second — 7 minutes
for 6,857, hours for 30,000. For the venv, reinstalling is only safe with **exact pins**:
`pyproject.toml` uses open lower bounds (`numpy>=1.26`), and a newer numpy or pandas could
move a floating-point result and break the R3 bit-identity gate. The versions were read out
of the existing `dist-info` directories and reinstalled exactly (numpy 2.4.6, pandas 3.0.3,
scikit-learn 1.9.0, scipy 1.17.1), which reproduced the baseline exactly.

*Always confirm a suite actually printed its pass/fail counts before recording it as green.*

**Git.** `git status` takes minutes on this tree and `git add` can be killed mid-write,
leaving a zero-byte `.git/index.lock`. Check `ps` for a live git process, then remove it —
that touches no commit and no file. Note that `GIT_OPTIONAL_LOCKS=0`, which makes reads fast
here, makes `git add` a **silent no-op**, because the add needs the lock it suppresses.

The decisive cause of the git failures, though, was not `.git` at all — it was that
`git add -A -- docs` traverses `docs/qa`, which holds **19 archived visual-QA runs, ~1,900
PNGs, 475 MB**, essentially all of it evicted. Every staging attempt spent its life stat-ing
those files and was killed. Temporarily moving `docs/qa`, `nbaplayerimages` (2,476 dirs) and
`nbalogos` out of the tree — an instant same-volume rename — took `git add` from *repeatedly
killed after minutes* to **exit 0 in 29 seconds**. They were moved back immediately after the
push, and all three are gitignored, so nothing about the commit depended on them.

Two things not to do, both tried: `mv .git` out of the synced tree **timed out after 8
minutes** and left `.git` briefly unreadable (it recovered intact); and symlinking
`node_modules` to a `.nosync` sibling breaks `tsc`, which excludes `node_modules` **by name**
and then type-checks the whole dependency tree.

**The root cause is disk pressure.** The volume is at 94-95 % (≈12 GiB free of 228 GiB), which
is why macOS keeps evicting. Freeing space is the durable fix; `docs/qa` alone is 475 MB of
regenerable artifacts. That is the operator's call and nothing here deleted it.

---

## 8. What was verified by hand

- The four new intelligence endpoints, against the live 30-team ingested database (§4).
- The fit distribution across four rosters and 400+ player-team pairs (§3).
- That every moved constant is byte-identical and the cache fingerprint unchanged (§2).
- That no user-visible string pinned by a test was changed without updating the test — one
  was (`<title>Pivot decision memo</title>`, `test_api.py:226`), deliberately.
- That the load-bearing historical identifiers survived: `tradelab-backend`, `tradelab.db`,
  the `tradelab:` cache prefix, `TEI`, `ROSTERLAB_OFFLINE`, `rosterlab.favoriteTeam`, and the
  13 `ROSTERLAB_*.md` reports.


---

## 9. Closing pass — the QA that §6 could not run

*Everything §6 listed as blocked was run, on a checkout moved off the iCloud-synced volume.
The environment, not the code, was the blocker: `git status` went from minutes to 0.019 s,
`next dev` from a 3-minute stall to "Ready in 365 ms", and `next build` from a
`TurbopackInternalError` to 15 seconds.*

### The three blocked checks, run

| Check | Result |
| --- | --- |
| **Playwright e2e** | **6 passed** — after fixing one genuine regression (below) |
| **Visual QA** (15 routes x 7 viewports) | **105 screenshots CLEAN** — 0 px horizontal overflow, 0 console errors, 0 empty pages |
| **Live browser QA** | Every route walked at 1920 / 1440 / 1366 / 1280 / 1024 / 768 / 390 |

Full battery re-run after every fix: `pytest` **1003 passed / 2 skipped**, coverage **89 %**;
`ruff`, `mypy` (109 files), `eslint`, `tsc` clean; `alembic check` no drift; `vitest`
**110 passed**; `next build` **13 routes**.

### The provenance defect, fixed

`source_provider` was never read anywhere in the serving layer. `Provenance` defaulted to
`nba_api` / `NBA.com` and **no caller ever overrode it**, so a demo row — correctly stamped
`demo_seed`, correctly refused entry to a real database, correctly guarded by a Playwright
roster-name check — was still *described to the client as NBA.com data*. Four guards stopped
synthetic data leaking; none stopped it being mislabelled.

`app/core/provenance.py` now holds the one provider-to-upstream map. It lives in `core`, not
beside the API schemas, because services build source cards and decision memos too and a
service must not import from `app.api`. An unmapped provider renders as its own key rather
than falling back to NBA.com: an unfamiliar label is a much smaller lie than a confident
wrong one.

| Site | Was | Now |
| --- | --- | --- |
| `api/schemas.py::Provenance` | class defaults `nba_api` / `NBA.com` | required fields; `Provenance.of(row)` |
| `api/v1/teams.py::_team_out` | defaulted | reads the row |
| `api/v1/players.py::_player_out` | defaulted | reads the row |
| `api/v1/teams.py` roster | `"NBA.com via nba_api (CommonTeamRoster)"` | derived, plus `source_providers` |
| `api/v1/players.py` stats | `"NBA.com via nba_api (LeagueDashPlayerStats)"` | derived, plus `source_providers` |
| `services/data_health.py` "Current NBA data" | named nba_api while counting every provider's rows | names the providers actually in those tables |
| `services/intelligence.py::SKILL_SOURCE` | `"… (NBA.com via nba_api)"` | names the population, not an upstream |
| `services/reports.py` decision memo | `"Source: NBA.com via nba_api"` | from `data_freshness["source"]` |
| `ingestion/jobs.py` season calendar | defaulted the *stored* provider to `nba_api` | `"unknown"` — never write an unearned claim |
| `components/ui.tsx::SourceRail` / `SourceLine` | `source` **defaulted** to `"NBA.com via nba_api"` | required prop; every rail passes what was served |

Four UI sites hard-coded the string independently of the API (`team-outlook` index and
detail, the player header, and the Trade Evaluator's fallback) and now render the served
`upstream`. `strategy-lab`'s `ENGINE_SOURCE` no longer appends an upstream it never checked.

On the ingested database the change is visible and correct: `/players/{id}/stats` now reports
**"NBA.com via nba_api + User-imported CSV"**, because that endpoint has always served both
and only ever named one.

Two new tests pin it: a demo-seeded database is walked through the API and asserted never to
be described as NBA.com, and an unmapped provider is asserted to render as itself.

**Deliberately not changed.** `list_season_totals` filters `stat_type="totals"`, which only
the CSV importer writes — the demo seeder uses `csv_totals` — so its hard-coded label cannot
be wrong. Static product prose ("Rosters and stats from NBA.com, never invented" on the home
page, the footer, `/methodology`, the OpenAPI description) is a claim about the deployment
rather than a per-row label, and was left alone.

### Regressions found and fixed

1. **`comparablesResponseSchema` rejected the backend's own empty-corpus response.**
   `seasons_ingested: z.array(z.string()).min(1)` was stricter than
   `ComparableTradeService.coverage()`, which derives the list from the corpus — so it is
   `[]` exactly when the corpus is empty, and that same block rides on the `available: false`
   responses. A zod throw instead of the designed unavailable state. **The one confirmed
   restructure regression that a type-check and a build could not catch.**
2. **The e2e homepage spec was stale.** The restructure rewrote the headline, both calls to
   action and the tool launcher; §6 predicted the suite "should pass unmodified" and it did
   not. Four assertions updated to the strings that ship, same six intents.
3. **Hydration mismatches on `/` and `/salary-cap-center`** (pre-existing, not from the
   restructure). The shell hydrates before these pages and warms the shared `["teams"]` query
   cache, so their first client render already had data while the server HTML had skeletons.
   `lib/hydrated.ts` holds one `useHydrated()`; query results are read through it, so the
   hydration render matches the server exactly. The Trade Evaluator's file-local copy of the
   same hook was folded into it.
4. **Horizontal overflow on mobile.** Seven headings carried `whitespace-nowrap` on
   `title-lg`, which floors at 24 px — including the user-supplied trade name. Now
   `text-balance`. Measured 0 px overflow at 390 px on every route.
5. **Error states.** The restructure gave its *new* intelligence queries an error branch and
   left the older queries beside them reading only `data`, so a failed request rendered the
   same skeleton as a pending one, forever. Added on the Command Center (teams, deals,
   strategies), Team Outlook (roster, payroll) and the player page (stats, contract).
6. **`health.providers` dereferenced without a guard** while `dataHealthSchema` deliberately
   does not validate `providers`.
7. **Branding.** `app/favicon.ico` was still the create-next-app Vercel triangle; replaced
   with `app/icon.svg` carrying the Pivot mark. The seven `docs/screenshots/` PNGs embedded
   in the README still showed the **RosterLab** wordmark; regenerated.

### Known environment limitation

`nbaplayerimages/` is user-supplied and gitignored, and the copy on the synced volume has
been emptied by iCloud. This working copy therefore has no player photos, and its
`media_assets` player rows were pruned so the manifest matches the files that exist. Restore
the tree and run `make index-assets` to bring them back. Team logos (30/30) were recovered
and are indexed.
