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

await shot("/", "landing");

// Decision room with a focal team selected
await page.goto("http://localhost:3000/decision-room", { waitUntil: "networkidle" });
await page.locator("select").first().selectOption({ index: 2 });
await page.waitForTimeout(2500);
await page.screenshot({ path: `${OUT}decision-room.png` });
console.log("captured decision-room");

// Team page (first team from API)
const teams = await (await fetch("http://localhost:8000/api/v1/teams")).json();
const bos = teams.find((t) => t.abbreviation === "BOS") ?? teams[0];
await shot(`/teams/${bos.id}`, "team-page", 2500);

// Trade detail (existing saved trade)
const trades = await (await fetch("http://localhost:8000/api/v1/trades")).json();
if (trades.length > 0) {
  await shot(`/trades/${trades[trades.length - 1].id}`, "trade-evaluation", 3500);
}

await shot("/trade-builder", "trade-builder", 1500);
await shot("/data-health", "data-health", 2000);

await browser.close();
