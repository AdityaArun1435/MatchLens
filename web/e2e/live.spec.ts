import { expect, test } from "@playwright/test";

test("live replay of the final at 60x: the clock advances and the first goal appears with a caption", async ({ page }) => {
  await page.goto("/match/3869685");
  await page.getByTestId("watch-live").click();
  await expect(page.getByTestId("live-mode")).toBeVisible();
  await expect(page.getByTestId("live-status")).toContainText("Replay");

  await page.getByTestId("live-speed").getByRole("button", { name: "60x" }).click();
  await expect(page.getByTestId("live-speed").getByRole("button", { name: "60x" })).toHaveAttribute("aria-pressed", "true");

  // the clock advances by itself
  const first = await page.getByTestId("live-clock").innerText();
  await expect.poll(async () => page.getByTestId("live-clock").innerText(), { timeout: 15_000 }).not.toBe(first);

  // jump to the 22nd minute; Messi's penalty is at 23'
  await page.getByTestId("live-scrubber").fill("1320");
  await expect(page.locator('[data-moment-type="goal"]').first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("live-score")).toHaveText("1-0");
  await expect(page.getByTestId("live-caption")).toContainText("Goal! Lionel Messi");
  await expect(page.getByTestId("live-ticker")).toContainText("GOAL");
  await expect(page.getByTestId("live-clock")).toHaveText(/^(23|24|25)'$/);
});

test("pause holds the clock and resume continues it", async ({ page }) => {
  await page.goto("/match/3869685");
  await page.getByTestId("watch-live").click();
  await page.getByTestId("live-speed").getByRole("button", { name: "60x" }).click();
  await expect.poll(async () => page.getByTestId("live-clock").innerText()).not.toBe("1'");
  await page.getByTestId("live-pause").click();
  await expect(page.getByTestId("live-status")).toContainText("Paused");
  const held = await page.getByTestId("live-clock").innerText();
  await page.waitForTimeout(1500);
  expect(await page.getByTestId("live-clock").innerText()).toBe(held);
  await page.getByTestId("live-pause").click();
  await expect.poll(async () => page.getByTestId("live-clock").innerText(), { timeout: 15_000 }).not.toBe(held);
});

test("at full time 'Read the recap' opens the cached recap", async ({ page }) => {
  await page.goto("/match/3869685");
  await page.getByTestId("audience-toggle").getByRole("button", { name: "Broadcaster" }).click(); // a combination no other test caches
  await page.getByTestId("recap-generate").click(); // cache one recap first (fake model)
  await expect(page.getByTestId("recap-result")).toBeVisible();
  await page.getByTestId("watch-live").click();
  await page.getByTestId("live-speed").getByRole("button", { name: "60x" }).click();
  await page.getByTestId("live-scrubber").fill("8800"); // a few seconds before the end of the shootout
  await expect(page.getByTestId("live-fulltime")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("live-fulltime")).toContainText("Argentina 3-3 France");
  await expect(page.getByTestId("live-clock")).toHaveText("Pens");
  await page.getByTestId("live-read-recap").click();
  await expect(page.getByTestId("recap-result")).toBeVisible();
  await expect(page.getByTestId("recap-generate")).toHaveCount(0);
});

test("live replay without the backend shows a clear message", async ({ page }) => {
  await page.routeWebSocket(/\/live/, (ws) => ws.close());
  await page.goto("/match/3869685");
  await page.getByTestId("watch-live").click();
  await expect(page.getByTestId("live-error")).toContainText("not connected");
});
