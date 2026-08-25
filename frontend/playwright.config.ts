import { defineConfig } from "@playwright/test";

/**
 * End-to-end tests run against a live local stack (backend :8000 + frontend :3000).
 * They do NOT call NBA.com — they exercise the app against whatever database
 * `DATABASE_URL` points at.
 *
 * CI points `DATABASE_URL` at a dedicated, freshly migrated database seeded by
 * `python -m app.cli seed-demo` (synthetic; see backend/app/ingestion/demo_seed.py), so
 * the suite never depends on a developer's ingested data and never writes test entities
 * into it.
 *
 * **A running dev server is not reusable, and R7 made that explicit.** `reuseExistingServer`
 * defaulted to true, so `make e2e` seeded the dedicated database, then Playwright attached
 * to whatever uvicorn a developer already had up — pointed at their ingested database —
 * and ran the whole suite against the wrong data while writing its fixture trades into it.
 * That is the pollution R1-7 removed, reintroduced by the harness whenever a dev server
 * happened to be running, which is the common case. It is now opt-in via
 * `E2E_REUSE_SERVER=1`, and `guards.spec.ts` refuses to run against a database that is not
 * the synthetic demo league.
 *
 * Overrides:
 *   E2E_NO_SERVER=1      — attach to servers you already started
 *   E2E_REUSE_SERVER=1   — attach to a matching server if one is already listening
 *   E2E_BACKEND_CMD=…    — how to launch uvicorn (CI has it on PATH, dev uses .venv)
 *   E2E_FRONTEND_CMD=…   — `npm run dev` locally, `npm start` against a build in CI
 */
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  retries: 0,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    screenshot: "only-on-failure",
  },
  webServer: process.env.E2E_NO_SERVER
    ? undefined
    : [
        {
          command:
            process.env.E2E_BACKEND_CMD ??
            "cd ../backend && .venv/bin/uvicorn app.main:app --port 8000",
          url: "http://localhost:8000/api/v1/health",
          reuseExistingServer: Boolean(process.env.E2E_REUSE_SERVER),
          timeout: 60_000,
        },
        {
          command: process.env.E2E_FRONTEND_CMD ?? "npm run dev",
          url: "http://localhost:3000",
          reuseExistingServer: Boolean(process.env.E2E_REUSE_SERVER),
          timeout: 120_000,
        },
      ],
});
