import { expect, test } from "@playwright/test";

/**
 * Core RosterLab flows against a live local stack with an ingested database
 * (`make sync-data && make train && make score`, plus `make index-assets` /
 * `make import-stats-csv` for full coverage). No NBA.com calls happen here.
 */

test("overview presents the platform with honest data status", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: "RosterLab — home" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Build the next move." })).toBeVisible();
  // primary and secondary calls to action
  await expect(page.getByRole("link", { name: "Open the Trade Evaluator" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Explore the platform" })).toBeVisible();
  // the tool launcher reaches every active module in one click
  await expect(page.getByRole("heading", { name: "Front-office tools" })).toBeVisible();
  // roadmap items are described, never presented as usable
  await expect(page.getByText("Contract Predictor")).toBeVisible();
});

test("renamed modules keep old links working", async ({ page }) => {
  for (const [oldPath, heading] of [
    ["/trade-machine", "Trade Evaluator"],
    ["/compare", "Decision board"],
    ["/player-lab", "Player Explorer"],
  ] as const) {
    await page.goto(oldPath);
    await expect(page.getByRole("heading", { name: heading, level: 1 })).toBeVisible({
      timeout: 20_000,
    });
  }
});

test("data health reports sources and never hides a missing one", async ({ page }) => {
  await page.goto("/data-health");
  await expect(page.getByText("Current NBA data").first()).toBeVisible({ timeout: 20_000 });
  // contracts are not imported by default — that must be stated, not glossed over
  await expect(page.getByText(/not imported|not configured|unavailable/i).first()).toBeVisible();
});

test("player explorer lists imported season totals", async ({ page }) => {
  await page.goto("/player-explorer");
  await expect(page.getByRole("heading", { name: /Player Explorer/i, level: 1 })).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByText(/season totals/i).first()).toBeVisible({ timeout: 20_000 });
});

test("full flow: team outlook → strategy → trade evaluator → rules → evaluate → save → compare", async ({
  page,
}) => {
  // 1. Team Outlook: open a team
  await page.goto("/team-outlook");
  await page.getByRole("link", { name: /Celtics/ }).first().click();
  await expect(page.getByText(/team strategy/i).first()).toBeVisible({ timeout: 25_000 });

  // 2. Save a strategy
  await page.getByRole("button", { name: /Save strategy/i }).click();
  await expect(page.getByText(/Strategy saved/i).first()).toBeVisible({ timeout: 15_000 });

  // 3. Trade Evaluator, carrying the team through (exact name: "Trade Evaluator"
  //    in the nav also matches a loose /Trade/ pattern)
  await page.getByRole("link", { name: "Start a trade", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Trade Evaluator", level: 1 })).toBeVisible({
    timeout: 20_000,
  });

  // 4. Add a second team, then move a player with the accessible control
  await page.getByRole("button", { name: /Add team/i }).first().click();
  await page.getByRole("button", { name: /Atlanta Hawks|Hawks/ }).first().click();
  await page.getByRole("button", { name: /Send .* to/ }).first().click({ timeout: 20_000 });

  // 5. Live rules check reports one of the four honest states
  await expect(
    page
      .getByText(/Passes rules check|Fails rules check|Incomplete check|Not checked/)
      .first(),
  ).toBeVisible({ timeout: 25_000 });

  // 6. Evaluate and read the fan verdict
  await page.getByRole("button", { name: /Evaluate this deal/i }).click();
  await expect(
    page
      .getByText(/Strong fit|Mixed outcome|High-risk upside|Poor strategic fit|Cannot fully evaluate/)
      .first(),
  ).toBeVisible({ timeout: 40_000 });

  // 7. Save the deal → full report
  await page.getByLabel(/Deal name/i).fill("E2E RosterLab deal");
  await page.getByRole("button", { name: /^Save deal$/i }).click();
  await expect(page.getByRole("heading", { name: "E2E RosterLab deal" })).toBeVisible({
    timeout: 40_000,
  });

  // 8. Strategy Lab lists it
  await page.goto("/strategy-lab");
  await expect(page.getByText("E2E RosterLab deal").first()).toBeVisible({ timeout: 20_000 });
});
