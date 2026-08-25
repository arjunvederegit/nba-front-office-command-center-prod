// Capture documentation screenshots from a running local stack.
// Usage: node scripts/capture_screenshots.mjs   (requires frontend:3000 + backend:8000)
import { createRequire } from "node:module";
import { mkdirSync } from "fs";

// See scripts/visual_qa.mjs — node_modules lives under frontend/, not the repo root.
const requireFromFrontend = createRequire(
  new URL("../frontend/package.json", import.meta.url),
);
const { chromium } = requireFromFrontend("@playwright/test");

const OUT = decodeURIComponent(new URL("../docs/screenshots/", import.meta.url).pathname);
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

async function shot(path, name, extraWait = 1500) {
  await page.goto(`http://localhost:3000${path}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(extraWait);
  await page.screenshot({ path: `${OUT}${name}.png`, fullPage: false });
  console.log(`captured ${name}`);
}

await shot("/", "overview", 2500);

const teams = await (await fetch("http://localhost:8000/api/v1/teams")).json();
const bos = teams.find((t) => t.abbreviation === "BOS") ?? teams[0];
await shot(`/team-outlook/${bos.id}`, "team-outlook", 3000);

const trades = await (await fetch("http://localhost:8000/api/v1/trades")).json();
if (trades.length > 0) {
  await shot(`/trades/${trades[0].id}`, "deal-report", 3500);
}

await shot(`/trade-evaluator?team=${bos.id}`, "trade-evaluator", 3000);
await shot("/player-explorer", "player-explorer", 3000);
await shot("/strategy-lab", "strategy-lab", 2500);
await shot("/data-health", "data-health", 2500);

await browser.close();
