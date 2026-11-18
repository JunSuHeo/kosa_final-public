import { test, expect } from "@playwright/test";

test("실제 다섯 역할 검토의 화면과 근거 이동", async ({ page }) => {
  const id = process.env.LIVE_PREVIEW_PROJECT_ID;
  test.skip(
    !id,
    "Run explicitly against the live review verification project.",
  );
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewportSize({ width: 1600, height: 1100 });
  await page.goto(`/?project=${id}`);
  await page.getByRole("button", { name: "검토", exact: true }).click();
  await page
    .getByRole("button", { name: "역할별 AI 검토", exact: true })
    .click();
  await expect(page.locator(".role-progress")).toContainText("5/5 역할 완료");
  await page
    .getByRole("group", { name: "검토 역할" })
    .getByRole("button", { name: "보안 완료" })
    .click();
  await expect(page.locator(".role-finding")).toHaveCount(3);
  await page.screenshot({
    path: "../docs/screenshots/live-role-review.png",
    fullPage: true,
    animations: "disabled",
  });
  await page
    .getByRole("group", { name: "검토 역할" })
    .getByRole("button", { name: "UI/UX 완료" })
    .click();
  const evidence = page
    .locator(".finding-evidence")
    .filter({ hasText: "screen-" });
  if (await evidence.count()) {
    await evidence.first().click();
    await expect(
      page.getByRole("tab", { name: "와이어프레임" }),
    ).toHaveAttribute("aria-selected", "true");
    await expect(page.locator(".wire-page")).toBeVisible();
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".role-selector")).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/live-role-review-mobile.png",
    fullPage: true,
    animations: "disabled",
  });
  const panel = await page.locator(".side-panel").boundingBox();
  expect(panel!.x).toBeGreaterThanOrEqual(0);
  expect(panel!.x + panel!.width).toBeLessThanOrEqual(390);
  expect(errors).toEqual([]);
});
