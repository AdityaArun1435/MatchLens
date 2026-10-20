// Takes the README screenshots against the running app (start it first with .\start.ps1).
//   npm run screenshots                       -> docs/screenshots/*.png, real recaps (generated once, then cached)
// Needs recaps for analyst/medium in EN, HI and TA; the first run asks the local model for them and can take minutes.
import { mkdirSync } from "node:fs";
import path from "node:path";
import { chromium } from "@playwright/test";

const BASE = process.env.WEB_URL ?? "http://localhost:3000";
const MATCH = process.env.MATCH_ID ?? "3869685";
const out = path.resolve(import.meta.dirname, "..", "..", "docs", "screenshots");
mkdirSync(out, { recursive: true });

const browser = await chromium.launch();

async function matchPage(language, viewport, file, { openMoment = true, openReport = true } = {}) {
  const page = await browser.newPage({ viewport, deviceScaleFactor: 1 });
  await page.goto(`${BASE}/match/${MATCH}`);
  await page.getByTestId("final-score").waitFor();
  if (language !== "en") await page.getByTestId("language-toggle").getByRole("button", { name: language.toUpperCase() }).click();
  const generate = page.getByTestId("recap-generate");
  if (await generate.isVisible()) await generate.click();
  await page.getByTestId("recap-result").waitFor({ timeout: 15 * 60_000 });
  if (openMoment) {
    await page.getByTestId("moment-m_004").getByRole("button").click();
    await page.getByTestId("moment-panel").waitFor();
  }
  if (openReport) await page.getByTestId("report-toggle").last().click();
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(out, file), fullPage: true });
  await page.close();
  console.log("saved", file);
}

const desktop = { width: 1360, height: 900 };
for (const lang of ["en", "hi", "ta"]) await matchPage(lang, desktop, `match-${lang}.png`);

const picker = await browser.newPage({ viewport: desktop });
await picker.goto(BASE);
await picker.getByTestId("match-list").waitFor();
await picker.screenshot({ path: path.join(out, "picker.png") });
console.log("saved picker.png");

await matchPage("en", { width: 390, height: 844 }, "match-mobile-en.png", { openMoment: false, openReport: false });
await browser.close();
