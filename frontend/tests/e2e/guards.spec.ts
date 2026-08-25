import { expect, test } from "@playwright/test";

/**
 * What database is this suite actually talking to?
 *
 * R7 found that it was often the wrong one. `make e2e` builds and seeds a dedicated
 * database, but Playwright's `reuseExistingServer` defaulted to true, so whenever a
 * developer had `make dev` running the whole suite attached to *their* server — pointed at
 * their ingested data — and wrote its fixture trades into it. Every test still passed,
 * because the assertions are about product behaviour and the product behaves the same way
 * on either database. Silence was the failure mode.
 *
 * The config no longer reuses a server by default. This runs first anyway, because a
 * configuration flag is a claim and this is a measurement: the demo seeder names every
 * synthetic player `Demo <Team> <n>`, so one roster read settles it.
 */

const API = "http://localhost:8000/api/v1";

test("the suite is running against the synthetic demo league, not ingested NBA data", async ({
  request,
}) => {
  const teams = await (await request.get(`${API}/teams`)).json();
  expect(teams.length).toBeGreaterThan(0);

  const roster = await (await request.get(`${API}/teams/${teams[0].id}/roster`)).json();
  const names: string[] = (roster.roster ?? []).map(
    (entry: { full_name?: string; name?: string }) => entry.full_name ?? entry.name ?? "",
  );
  expect(names.length).toBeGreaterThan(0);

  const synthetic = names.filter((name) => name.startsWith("Demo "));
  expect(
    synthetic.length,
    `This suite writes fixture trades into whatever backend it reaches, so it must only ` +
      `ever reach the demo database. It found real-looking players (${names
        .slice(0, 3)
        .join(", ")}), which means it is pointed at ingested data — probably a dev server ` +
      `reused from \`make dev\`. Stop it, or set E2E_NO_SERVER=1 with a demo-seeded ` +
      `backend of your own.`,
  ).toBe(names.length);
});
