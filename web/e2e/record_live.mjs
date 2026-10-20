// Records docs/screenshots/live.gif: live replay of the 2022 final from the 79th minute, through Mbappé's goals at 80' and 81'.
// Start the app first (.\start.ps1); live replay needs the backend only. Needs Pillow in the project venv for the last step.
import { execFileSync } from "node:child_process";
import { mkdirSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { chromium } from "@playwright/test";

const BASE = process.env.WEB_URL ?? "http://localhost:3000";
const root = path.resolve(import.meta.dirname, "..", "..");
const frames = path.join(os.tmpdir(), "matchlens-live-frames");
rmSync(frames, { recursive: true, force: true });
mkdirSync(frames, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1000, height: 1420 } });
await page.goto(`${BASE}/match/3869685`);
await page.getByTestId("watch-live").click();
await page.getByTestId("live-mode").waitFor();
await page.getByTestId("live-pause").click();
await page.getByTestId("live-speed").getByRole("button", { name: "30x" }).click();
await page.getByTestId("live-scrubber").fill("5135"); // 78 minutes played, the clock reads 79'
await page.waitForFunction(() => document.querySelector('[data-testid="live-clock"]')?.textContent === "79'");
await page.waitForTimeout(500);

const start = Date.now();
let resumed = false;
let n = 0;
while (Date.now() - start < 20_000) {
  const t = Date.now() - start;
  if (!resumed && t > 1500) {
    await page.getByTestId("live-pause").click(); // resume
    resumed = true;
  }
  await page.screenshot({ path: path.join(frames, `${String(Date.now() - start).padStart(7, "0")}.png`) });
  n++;
  await page.waitForTimeout(120);
}
await browser.close();
console.log(`captured ${n} frames`);
const python = process.platform === "win32" ? path.join(root, ".venv", "Scripts", "python.exe") : path.join(root, ".venv", "bin", "python");
execFileSync(python, [path.join(root, "scripts", "make_gif.py"), frames, path.join(root, "docs", "screenshots", "live.gif"), "--width", "760"], { stdio: "inherit" });
