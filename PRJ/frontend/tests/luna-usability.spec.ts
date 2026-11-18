import { test, expect } from "@playwright/test";

test("Luna 산출물과 역할 검토를 데스크톱·모바일에서 조회한다", async ({ page }) => {
  const id = process.env.LUNA_PROJECT_ID;
  test.skip(!id, "Requires a dedicated Luna live verification project");
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  for (const viewport of [{ width: 1600, height: 1100 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await page.goto(`/?project=${id}`);
    await expect(page.getByRole("button", { name: "검토 중인 초안" })).toBeVisible();
    if (viewport.width < 600) {
      await page.getByRole("button", { name: "채팅", exact: true }).click();
      await expect(page.locator(".side-panel")).toHaveCount(0);
    }
    await page.getByRole("tab", { name: "PRD", exact: true }).click();
    await expect(page.locator(".prd-group").first()).toBeVisible();
    await page.getByRole("tab", { name: "와이어프레임" }).click();
    await expect(page.locator(".wire-thumbnail").first()).toBeVisible();
    await page.screenshot({ path: `../docs/screenshots/luna-wireframes-${viewport.width}.png`, fullPage: true });
    await page.getByRole("tab", { name: "유저플로우" }).click();
    await expect(page.locator(".react-flow__node").first()).toBeVisible();
    await page.getByRole("button", { name: "검토", exact: true }).click();
    await page.getByRole("button", { name: "역할별 AI 검토", exact: true }).click();
    await expect(page.locator(".role-progress")).toContainText("5/5 역할 완료");
    await page.getByRole("group", { name: "검토 역할" }).getByRole("button", { name: "UI/UX 완료" }).click();
    await expect(page.locator(".role-finding").first()).toBeVisible();
    await page.screenshot({ path: `../docs/screenshots/luna-review-${viewport.width}.png`, fullPage: true, animations: "disabled" });
    const panel = await page.locator(".side-panel").boundingBox();
    expect(panel).not.toBeNull();
    expect(panel!.x).toBeGreaterThanOrEqual(0);
    expect(panel!.x + panel!.width).toBeLessThanOrEqual(viewport.width);
  }
  expect(errors).toEqual([]);
});

test("접속 오류 뒤 다시 연결하면 Luna 프로젝트가 복원된다", async ({ page }) => {
  const id = process.env.LUNA_PROJECT_ID;
  test.skip(!id, "Requires a dedicated Luna live verification project");
  await page.route("**/health", (route) => route.abort());
  await page.goto(`/?project=${id}`);
  await expect(page.getByRole("alert")).toBeVisible();
  await page.unroute("**/health");
  await page.getByRole("button", { name: "다시 연결", exact: true }).click();
  await expect(page.getByRole("button", { name: "검토 중인 초안" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "프로젝트 제목" })).not.toHaveValue("");
});

test("Luna의 긴 PRD와 부분 실패 역할 검토를 모바일에서 조회한다", async ({ page }) => {
  const id = process.env.LUNA_PARTIAL_PROJECT_ID;
  test.skip(!id, "Requires a Luna project with a failed developer review");
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  for (const viewport of [{ width: 1600, height: 1100 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await page.goto(`/?project=${id}`);
    await expect(page.locator(".prd-group").first()).toBeVisible();
    if (viewport.width < 600) {
      await page.getByRole("button", { name: "채팅", exact: true }).click();
    }
    await page.locator(".prd-group").last().scrollIntoViewIfNeeded();
    await expect(page.locator(".prd-group").last()).toBeVisible();
    await page.getByRole("button", { name: "검토", exact: true }).click();
    await page.getByRole("button", { name: "역할별 AI 검토", exact: true }).click();
    await page.getByRole("group", { name: "검토 역할" }).getByRole("button", { name: "개발자 실패" }).click();
    await expect(page.getByRole("button", { name: "이 역할만 재시도" })).toBeEnabled();
    await expect(page.locator(".role-progress")).toContainText("1/5 역할 완료");
    await page.screenshot({ path: `../docs/screenshots/luna-partial-review-${viewport.width}.png`, fullPage: true });
  }
  expect(errors).toEqual([]);
});
