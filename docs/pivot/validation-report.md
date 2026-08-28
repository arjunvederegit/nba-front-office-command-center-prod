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

### Carried into R8 (documented, not fixed here)

1. **The API hard-codes provenance to NBA.com** regardless of a row's actual
   `source_provider`. Synthetic demo rows are correctly stamped and quarantined in storage
   but are *described* as NBA.com data when served. This is the one genuine honesty defect
   the audit found. It is first in [the R8 plan](r8-readiness.md) because it is small and
   because the claim is the product.
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

### Not run in this pass

- **Playwright e2e.** The suite requires a freshly seeded demo database and two free ports;
  it was not run end-to-end here. Its specs were updated for the rename (`Pivot — home`,
  `E2E Pivot deal`) and the h1 assertions it pins (`Trade Evaluator`, `Decision board`,
  `Player Explorer`) were deliberately left unchanged, so the suite should pass unmodified.
  **This is the highest-value thing to run before merging.**
- **Visual QA** (`make visual-qa`, 15 routes × 7 viewports). Not run. The route manifest was
  not touched because no route moved.
- **`docs/screenshots/`** still shows the RosterLab wordmark in all seven curated PNGs. They
  are embedded in the README and are now stale. Regenerating them needs a running stack.

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
