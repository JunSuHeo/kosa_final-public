import { login } from "./business-helpers";
import { test, expect } from "@playwright/test";
test.beforeEach(async ({ page }) => {
  await login(page);
});
test("실제 생성된 산출물의 화면 검증", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1600, height: 1250 });
  const id = process.env.LIVE_PREVIEW_PROJECT_ID;
  test.skip(
    !id,
    "Run explicitly against the generated live verification project.",
  );
  await page.goto(`/?project=${id}`);
  await expect(
    page.getByRole("button", { name: "작성 중인 초안" }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "화면 시안" }).click();
  await expect(page.locator(".wire-thumbnail").first()).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/live-wireframes.png",
    fullPage: true,
  });
  await page.getByRole("tab", { name: "기획 내용", exact: true }).click();
  await expect(page.locator(".prd-group").first()).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/live-workspace.png",
    fullPage: true,
  });
  await page.getByRole("tab", { name: "업무 흐름" }).click();
  expect(await page.locator(".react-flow__node").count()).toBeGreaterThan(0);
  await page.screenshot({
    path: "../docs/screenshots/live-flow.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
