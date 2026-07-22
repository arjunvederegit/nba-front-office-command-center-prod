// Capture documentation screenshots from a running local stack.
// Usage: node scripts/capture_screenshots.mjs   (requires frontend:3000 + backend:8000)
import { chromium } from "@playwright/test";
import { mkdirSync } from "fs";

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

await shot("/", "landing", 2500);

const teams = await (await fetch("http://localhost:8000/api/v1/teams")).json();
const bos = teams.find((t) => t.abbreviation === "BOS") ?? teams[0];
await shot(`/team-hub/${bos.id}`, "team-page", 3000);

const trades = await (await fetch("http://localhost:8000/api/v1/trades")).json();
if (trades.length > 0) {
  await shot(`/trades/${trades[0].id}`, "trade-evaluation", 3500);
}

await shot(`/trade-machine?team=${bos.id}`, "trade-builder", 3000);
await shot("/player-lab", "player-lab", 3000);
await shot("/data-status", "data-health", 2500);

await browser.close();
