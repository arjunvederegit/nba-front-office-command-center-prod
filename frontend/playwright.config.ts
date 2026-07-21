import { defineConfig } from "@playwright/test";

/**
 * End-to-end tests run against a live local stack (backend :8000 + frontend :3000)
 * with an already-ingested database. They do NOT call NBA.com — they exercise the
 * app against whatever the local database contains. CI does not run these against
 * external providers (see .github/workflows/ci.yml).
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
          command: "cd ../backend && .venv/bin/uvicorn app.main:app --port 8000",
          url: "http://localhost:8000/api/v1/health",
          reuseExistingServer: true,
          timeout: 30_000,
        },
        {
          command: "npm run dev",
          url: "http://localhost:3000",
          reuseExistingServer: true,
          timeout: 60_000,
        },
      ],
});
