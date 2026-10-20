import { expect, test } from "@playwright/test";

test("final: open a moment, explain it, generate an English analyst recap and read how it was checked", async ({ page }) => {
  // Match picker: the three preloaded matches
  await page.goto("/classic");
  await expect(page.getByTestId("match-list").locator("a")).toHaveCount(3);
  await page.getByTestId("match-card-3869685").click();
  await expect(page).toHaveURL(/\/classic\/match\/3869685$/);

  // Header and chart
  await expect(page.getByTestId("final-score")).toHaveText("3-3");
  await expect(page.getByTestId("home-team")).toHaveText("Argentina");
  await expect(page.getByTestId("result-detail")).toContainText("Argentina won 4-2 on penalties");
  await expect(page.getByTestId("xg-chart")).toBeVisible();
  await expect(page.locator('[data-testid^="goal-marker-"]')).toHaveCount(6);

  // Moments: the slider hides the less important ones
  await expect(page.getByTestId("moment-count")).toHaveText("showing 10 of 10");
  await page.getByTestId("importance-slider").fill("0.9");
  await expect(page.getByTestId("moment-count")).not.toHaveText("showing 10 of 10");
  await page.getByTestId("importance-slider").fill("0");

  // Open a moment and explain it
  await page.getByTestId("moment-m_004").getByRole("button").click();
  await expect(page.getByTestId("moment-panel")).toContainText("Kylian Mbappé");
  await expect(page.getByTestId("moment-panel")).toContainText("2-1 → 2-2");
  await page.getByTestId("explain-button").click();
  await expect(page.getByTestId("explain-result")).toContainText("Why it mattered");

  // English analyst recap
  await expect(page.getByTestId("audience-toggle").getByRole("button", { name: "Analyst" })).toHaveAttribute("aria-pressed", "true");
  await page.getByTestId("recap-generate").click();
  await expect(page.getByTestId("recap-result")).toBeVisible();
  await expect(page.getByTestId("recap-title")).toHaveText("Argentina 3-3 France");
  const paragraphs = page.getByTestId("recap-paragraph");
  expect(await paragraphs.count()).toBeGreaterThanOrEqual(5);
  await expect(paragraphs.last()).toContainText("Kick 1: France, Kylian Mbappé, scored.");
  await expect(page.getByTestId("quality-badge").first()).toHaveText("Stable");

  // A citation chip scrolls to and opens its moment
  await page.getByTestId("chip-m_001").first().click();
  await expect(page.getByTestId("moment-panel")).toContainText("Lionel Messi");

  // "How was this checked?"
  await page.getByTestId("report-toggle").last().click();
  await expect(page.getByTestId("attempt-1")).toContainText("paragraphs passed");
  await expect(page.getByTestId("chip-retries").last()).toHaveText("no retries");
  await expect(page.getByTestId("chip-dropped").last()).toHaveText("0 dropped");
});

test("Hindi shows its quality badge and keeps a paragraph in English with a note when translation fails the checks", async ({ page }) => {
  await page.goto("/classic/match/3869685");
  await page.getByTestId("language-toggle").getByRole("button", { name: "HI" }).click();
  await expect(page.getByTestId("quality-badge").first()).toHaveText("Machine-translated");
  await page.getByTestId("recap-generate").click();
  await expect(page.getByTestId("recap-result")).toBeVisible();
  // the canned model cannot translate, so every paragraph falls back to English with a note, none is dropped
  await expect(page.getByTestId("paragraph-note").first()).toContainText("Shown in English");
  await expect(page.getByTestId("chip-fallbacks").last()).not.toHaveText("0 in English");
});

test("backend offline gives a clear message", async ({ page }) => {
  await page.route("**/matches/3869685/summary", (route) => route.abort());
  await page.goto("/classic/match/3869685");
  await expect(page.getByTestId("error-notice")).toContainText("backend is not running");
});

test("Ollama not running gives a clear message when generating", async ({ page }) => {
  await page.route("**/matches/3869685/recap", (route) =>
    route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Cannot reach Ollama at http://localhost:11434." }) }),
  );
  await page.goto("/classic/match/3869685");
  await page.getByTestId("length-toggle").getByRole("button", { name: "Short" }).click(); // a combination nobody has generated
  await page.getByTestId("recap-generate").click();
  await expect(page.getByTestId("error-notice")).toContainText("Ollama is not running");
});

test("a cached recap shows instantly with no Generate click", async ({ page }) => {
  await page.goto("/classic/match/3869685");
  await page.getByTestId("audience-toggle").getByRole("button", { name: "Fan" }).click();
  await page.getByTestId("recap-generate").click();
  await expect(page.getByTestId("recap-result")).toBeVisible();
  await page.reload();
  await page.getByTestId("audience-toggle").getByRole("button", { name: "Fan" }).click();
  await expect(page.getByTestId("recap-result")).toBeVisible();
  await expect(page.getByTestId("recap-generate")).toHaveCount(0);
  await expect(page.getByTestId("report-toggle").last()).toContainText("How was this checked?");
});

test("Show English: per paragraph and for all paragraphs of a translated recap", async ({ page }) => {
  const translated = {
    match_id: 3869685, audience: "analyst", length: "medium", language: "hi", model: "m", generation_seconds: 1, cached: true, quality: "machine-translated",
    recap: { title: "अर्जेंटीना 3-3 फ्रांस", paragraphs: [
      { text: "पहला अनुच्छेद", cites: ["m_001"], language: "hi", note: null },
      { text: "Second paragraph stays English.", cites: ["m_002"], language: "en", note: "Shown in English" },
    ] },
    source_recap: { title: "Argentina 3-3 France", paragraphs: [
      { text: "First paragraph in English.", cites: ["m_001"], language: null, note: null },
      { text: "Second paragraph stays English.", cites: ["m_002"], language: null, note: null },
    ] },
    report: { method: "llm", attempts: [{ attempt: 1, items_total: 2, items_valid: 2, errors: [], llm_error: null }], retried: false, dropped: [], title_replaced: false, fallback_reason: null, notes: [],
      translation: { language: "hi", units: [], names_added: [], names_missing: [], seconds: 1, fallbacks: 1, retries: 0 } },
  };
  await page.route(/\/matches\/3869685\/recap\?.*language=hi/, (route) => route.fulfill({ json: translated }));
  await page.goto("/classic/match/3869685");
  await page.getByTestId("language-toggle").getByRole("button", { name: "HI" }).click();
  await expect(page.getByTestId("recap-result")).toBeVisible();
  await expect(page.getByTestId("english-source")).toHaveCount(0);
  await expect(page.getByTestId("english-toggle")).toHaveCount(1); // only the translated paragraph offers it
  await page.getByTestId("english-toggle").click();
  await expect(page.getByTestId("english-source")).toContainText("Translated from the checked English text");
  await expect(page.getByTestId("english-source")).toContainText("First paragraph in English.");
  await page.getByTestId("english-toggle").click();
  await expect(page.getByTestId("english-source")).toHaveCount(0);
  await page.getByTestId("english-all-toggle").check();
  await expect(page.getByTestId("english-source")).toHaveCount(1);
  await expect(page.getByTestId("english-title")).toHaveText("Argentina 3-3 France");
});

test("desktop: the moments card starts level with the recap card", async ({ page }) => {
  await page.setViewportSize({ width: 1360, height: 900 });
  await page.goto("/classic/match/3869685");
  const recap = await page.getByTestId("recap-panel").boundingBox();
  const moments = await page.getByTestId("moments-scroll").boundingBox();
  expect(recap && moments).toBeTruthy();
  expect(Math.abs(recap!.y - (moments!.y - 90))).toBeLessThan(140); // card padding and heading sit above the list
  await page.getByTestId("moment-m_004").getByRole("button").click();
  await page.mouse.wheel(0, 400);
  const after = await page.getByTestId("moments-scroll").boundingBox();
  expect(after).toBeTruthy();
});

test("phone: the xG chart is tall and scrolls sideways instead of shrinking", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/classic/match/3869685");
  const chart = page.getByTestId("xg-scroll");
  await expect(chart).toBeVisible();
  const box = await chart.boundingBox();
  expect(box!.height).toBeGreaterThan(300);
  const scrollable = await chart.evaluate((el) => el.scrollWidth > el.clientWidth);
  expect(scrollable).toBe(true);
  const overflowPage = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  expect(overflowPage).toBe(false);
});
