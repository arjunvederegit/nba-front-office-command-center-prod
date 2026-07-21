import { expect, test } from "@playwright/test";

/**
 * Full decision flow: open a team → create a scenario → construct a trade →
 * validate → save → compare → export report. Requires an ingested local database
 * (`make sync-data && make train && make score`).
 */

test("landing shows honest data status", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Structured decisions")).toBeVisible();
  await expect(page.getByText(/data synced|full data health/).first()).toBeVisible();
});

test("data health page reports providers and tables", async ({ page }) => {
  await page.goto("/data-health");
  await expect(page.getByRole("heading", { name: "Data health" })).toBeVisible();
  await expect(page.getByText("nba api", { exact: false }).first()).toBeVisible();
  // contracts provider is honestly reported as not configured by default
  await expect(page.getByText("not configured").first()).toBeVisible();
});

test("decision room → scenario → trade builder → validate → save → report", async ({
  page,
}) => {
  // 1. Decision room: pick a focal team
  await page.goto("/decision-room");
  const teamSelect = page.getByLabel("Focal team").or(page.locator("select").first());
  await teamSelect.selectOption({ index: 2 });
  await expect(page.getByText("Roster diagnosis", { exact: false })).toBeVisible();

  // 2. Save scenario
  await page.getByPlaceholder(/win-now push/).fill("E2E scenario");
  await page.getByRole("button", { name: "Save scenario" }).click();
  await expect(page.getByText("Scenario saved", { exact: false })).toBeVisible({
    timeout: 15_000,
  });

  // 3. Trade builder: two teams
  await page.goto("/trade-builder");
  const addTeam = page.getByLabel("Add team to trade");
  await addTeam.selectOption({ index: 1 });
  await addTeam.selectOption({ index: 1 });
  await expect(page.locator("header span.font-mono").first()).toBeVisible({ timeout: 20_000 });

  // 4. Move a player each way using the accessible buttons
  const sendButtons = page.getByRole("button", { name: /Send .* to/ });
  await page.locator(".group").first().hover();
  await sendButtons.first().click();
  await expect(page.getByText("Outgoing")).toBeVisible();

  // 5. Backend validation appears (never frontend-decided)
  await expect(page.getByText("Legality (backend-authoritative)")).toBeVisible();
  await expect(
    page
      .getByText(/Verified legal|Conditionally valid|Verified illegal|Not evaluated/)
      .first(),
  ).toBeVisible({ timeout: 20_000 });

  // 6. Save and open full evaluation
  await page.getByLabel("Trade name").fill("E2E test deal");
  await page.getByRole("button", { name: /Save & open full evaluation/ }).click();
  await expect(page.getByRole("heading", { name: "E2E test deal" })).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText("Composite utility", { exact: false })).toBeVisible();
  await expect(page.getByText("Rule-by-rule legality")).toBeVisible();

  // 7. Report export links exist
  await expect(page.getByRole("link", { name: "Report (MD)" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Report (print)" })).toBeVisible();

  // 8. Compare page lists the saved trade
  await page.goto("/compare");
  await expect(page.getByText("E2E test deal").first()).toBeVisible();
});
