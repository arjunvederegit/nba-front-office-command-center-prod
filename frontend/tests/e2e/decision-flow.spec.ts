import { expect, test } from "@playwright/test";

/**
 * Core RosterLab flows against a live local stack with an ingested database
 * (`make sync-data && make train && make score`, plus `make index-assets` /
 * `make import-stats-csv` for full coverage). No NBA.com calls happen here.
 */

test("home shows brand, honest data badges, and the team picker", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: "RosterLab home" })).toBeVisible();
  await expect(page.getByText("Run your front office", { exact: false })).toBeVisible();
  await expect(page.getByText(/NBA data synced|no data synced/).first()).toBeVisible();
  // 30-team picker grid
  await expect(page.getByRole("button", { name: /Boston Celtics/ })).toBeVisible();
});

test("data status reports source cards and honest gaps", async ({ page }) => {
  await page.goto("/data-status");
  await expect(page.getByText("Current NBA data").first()).toBeVisible();
  await expect(page.getByText("Contracts", { exact: false }).first()).toBeVisible();
  // contracts are not imported by default — the page must say so, not show all-green
  await expect(page.getByText(/not configured|unavailable/i).first()).toBeVisible();
});

test("player lab lists imported totals with per-game toggle", async ({ page }) => {
  await page.goto("/player-lab");
  await expect(page.getByRole("heading", { name: /Player Lab/i })).toBeVisible({
    timeout: 15_000,
  });
  // either real imported data or the honest empty state — both mention season totals
  await expect(page.getByText(/season totals/i).first()).toBeVisible({ timeout: 20_000 });
});

test("full flow: team hub → strategy → trade machine → rules → save → compare", async ({
  page,
}) => {
  // 1. Team Hub: open a team
  await page.goto("/team-hub");
  await page.getByRole("link", { name: /Celtics/ }).first().click();
  await expect(page.getByText("Choose your team strategy")).toBeVisible({ timeout: 20_000 });

  // 2. Save a strategy
  await page.getByRole("button", { name: "Save strategy" }).click();
  await expect(page.getByText(/Strategy saved/).first()).toBeVisible({ timeout: 15_000 });

  // 3. Trade Machine via the header CTA (carries ?team=)
  await page.getByRole("link", { name: "Start a trade" }).click();
  await expect(page.getByRole("heading", { name: "Trade Machine" })).toBeVisible();
  const addTeam = page.getByLabel("Add team to trade");
  await addTeam.selectOption({ index: 1 });

  // 4. Move a player with the accessible buttons
  await page.locator(".group").first().hover();
  await page.getByRole("button", { name: /Send .* to/ }).first().click();
  await expect(page.getByText("Outgoing")).toBeVisible();

  // 5. Live rules check (backend-authoritative, honest states)
  await expect(page.getByText("Trade rules check")).toBeVisible();
  await expect(
    page.getByText(/Passes rules check|Fails rules check|Incomplete check|Not checked/).first(),
  ).toBeVisible({ timeout: 20_000 });

  // 6. Inline evaluation with fan verdict
  await page.getByRole("button", { name: "Evaluate this deal" }).click();
  await expect(page.getByText("Deal evaluation")).toBeVisible({ timeout: 30_000 });
  await expect(
    page.getByText(/Strong fit|Mixed outcome|High-risk upside|Poor strategic fit|Cannot fully evaluate/).first(),
  ).toBeVisible();

  // 7. Advanced analysis discloses
  await page.getByRole("button", { name: "Show advanced analysis" }).click();
  await expect(page.getByText("Component scores")).toBeVisible();

  // 8. Save the deal → full report page
  await page.getByLabel("Deal name").fill("E2E RosterLab deal");
  await page.getByRole("button", { name: "Save deal" }).click();
  await expect(page.getByRole("heading", { name: "E2E RosterLab deal" })).toBeVisible({
    timeout: 30_000,
  });

  // 9. Compare page lists it
  await page.goto("/compare");
  await expect(page.getByText("E2E RosterLab deal").first()).toBeVisible();
});
