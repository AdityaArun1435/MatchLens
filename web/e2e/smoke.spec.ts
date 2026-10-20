import { expect, test } from "@playwright/test";

test("final: open a moment, explain it, generate an English analyst recap and read how it was checked", async ({ page }) => {
  // Match picker: the three preloaded matches
  await page.goto("/");
  await expect(page.getByTestId("match-list").locator("a")).toHaveCount(3);
  await page.getByTestId("match-card-3869685").click();
  await expect(page).toHaveURL(/\/match\/3869685$/);

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
  await page.goto("/match/3869685");
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
  await page.goto("/match/3869685");
  await expect(page.getByTestId("error-notice")).toContainText("backend is not running");
});

test("Ollama not running gives a clear message when generating", async ({ page }) => {
  await page.route("**/matches/3869685/recap", (route) =>
    route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Cannot reach Ollama at http://localhost:11434." }) }),
  );
  await page.goto("/match/3869685");
  await page.getByTestId("recap-generate").click();
  await expect(page.getByTestId("error-notice")).toContainText("Ollama is not running");
});
