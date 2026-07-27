// Visual QA harness: screenshots every required route at every required viewport,
// and reports console errors + horizontal overflow per page.
//
// Usage (from frontend/, where @playwright/test resolves):
//   node ../scripts/visual_qa.mjs [outDir] [routeFilter]
// Requires the local stack running (frontend :3000, backend :8000).

import { chromium } from "@playwright/test";
import { mkdirSync, writeFileSync } from "fs";

const OUT = decodeURIComponent(
  new URL(`../${process.argv[2] ?? "docs/qa/current"}/`, import.meta.url).pathname,
);
const FILTER = process.argv[3] ?? "";
mkdirSync(OUT, { recursive: true });

const VIEWPORTS = [
  { name: "1920x1080", width: 1920, height: 1080 },
  { name: "1440x900", width: 1440, height: 900 },
  { name: "1366x768", width: 1366, height: 768 },
  { name: "1280x800", width: 1280, height: 800 },
  { name: "1024x768", width: 1024, height: 768 },
  { name: "768x1024", width: 768, height: 1024 },
  { name: "390x844", width: 390, height: 844 },
];

const base = "http://localhost:3000";
const api = "http://localhost:8000/api/v1";

const teams = await (await fetch(`${api}/teams`)).json();
const team = teams.find((t) => t.abbreviation === "BOS") ?? teams[0];
const trades = await (await fetch(`${api}/trades`)).json();

const ROUTES = [
  { name: "overview", path: "/" },
  { name: "trade-empty", path: "/trade-evaluator" },
  { name: "trade-populated", path: `/trade-evaluator?team=${team.id}` },
  { name: "strategy-lab", path: "/strategy-lab" },
  { name: "player-explorer", path: "/player-explorer" },
  { name: "team-outlook-index", path: "/team-outlook" },
  { name: "team-outlook", path: `/team-outlook/${team.id}` },
  { name: "salary-cap-center", path: `/salary-cap-center?team=${team.id}` },
  { name: "methodology", path: "/methodology" },
  { name: "data-health", path: "/data-health" },
  ...(trades.length
    ? [{ name: "trade-result", path: `/trades/${trades[0].id}` }]
    : []),
].filter((r) => !FILTER || r.name.includes(FILTER));

const browser = await chromium.launch();
const report = [];

for (const viewport of VIEWPORTS) {
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  const errors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text().slice(0, 200));
  });
  page.on("pageerror", (err) => errors.push(`pageerror: ${String(err).slice(0, 200)}`));

  for (const route of ROUTES) {
    errors.length = 0;
    try {
      await page.goto(base + route.path, { waitUntil: "networkidle", timeout: 30000 });
    } catch {
      await page.goto(base + route.path, { waitUntil: "domcontentloaded", timeout: 30000 });
    }
    await page.waitForTimeout(1400);

    const overflow = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));

    await page.screenshot({
      path: `${OUT}${route.name}__${viewport.name}.png`,
      fullPage: viewport.width >= 1024,
    });

    report.push({
      route: route.name,
      viewport: viewport.name,
      horizontalOverflowPx: Math.max(0, overflow.scrollWidth - overflow.clientWidth),
      consoleErrors: [...errors],
    });
  }
  await context.close();
}

await browser.close();

const problems = report.filter(
  (r) => r.horizontalOverflowPx > 0 || r.consoleErrors.length > 0,
);
writeFileSync(`${OUT}report.json`, JSON.stringify({ report, problems }, null, 2));
console.log(`captured ${report.length} screenshots into ${OUT}`);
if (problems.length === 0) {
  console.log("CLEAN: no horizontal overflow, no console errors");
} else {
  console.log(`PROBLEMS (${problems.length}):`);
  for (const p of problems) {
    console.log(
      `  ${p.route} @ ${p.viewport}: overflow=${p.horizontalOverflowPx}px errors=${p.consoleErrors.length ? p.consoleErrors[0] : 0}`,
    );
  }
}
