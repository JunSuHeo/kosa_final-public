import { expect, test } from "@playwright/test";
import { begin, draft, login } from "./business-helpers";
test("작업 화면 너비를 드래그로만 조절하고 복원하며 모바일에서는 전환한다", async ({
  page,
}) => {
  await login(page);
  await begin(page);
  await draft(page);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const divider = page.getByRole("separator", {
    name: "대화와 산출물 너비 조절",
  });
  const left = page.locator(".side-panel");
  const right = page.locator(".workspace");
  await expect(divider).toBeVisible();
  const original = (await left.boundingBox())!.width;
  const box = (await divider.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + 200);
  await page.mouse.down();
  await page.mouse.move(box.x + 160, box.y + 200, { steps: 12 });
  await page.mouse.up();
  await expect(divider).not.toBeFocused();
  expect((await left.boundingBox())!.width).toBeGreaterThan(original + 130);
  const adjusted = (await left.boundingBox())!.width;
  await page.reload();
  await expect(divider).toBeVisible();
  expect(Math.abs((await left.boundingBox())!.width - adjusted)).toBeLessThan(
    2,
  );
  expect(await divider.evaluate((element) => element.tabIndex)).toBe(-1);
  for (const key of ["ArrowLeft", "ArrowRight", "Home", "End"])
    await page.keyboard.press(key);
  expect((await left.boundingBox())!.width).toBeCloseTo(adjusted, 0);
  const dragTo = async (x: number) => {
    const handle = (await divider.boundingBox())!;
    await page.mouse.move(handle.x + handle.width / 2, 300);
    await page.mouse.down();
    await page.mouse.move(x, 300, { steps: 8 });
    await page.mouse.up();
  };
  await dragTo(0);
  expect((await left.boundingBox())!.width).toBeGreaterThanOrEqual(320);
  await dragTo(1440);
  expect((await right.boundingBox())!.width).toBeGreaterThanOrEqual(419);
  await divider.dblclick();
  await expect(divider).not.toBeFocused();
  expect(Math.abs((await left.boundingBox())!.width - original)).toBeLessThan(
    2,
  );
  await page.getByRole("button", { name: "패널 접기 펼치기" }).click();
  await expect(divider).toHaveCount(0);
  expect((await right.boundingBox())!.width).toBeGreaterThan(1300);
  await page.getByRole("button", { name: "패널 접기 펼치기" }).click();
  await expect(divider).toBeVisible();
  await page.screenshot({
    path: "test-results/hplan-workspace-resize.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1200, height: 900 });
  await dragTo(1200);
  expect((await right.boundingBox())!.width).toBeGreaterThanOrEqual(419);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(divider).toBeHidden();
  await expect(left).toBeVisible();
  await page.getByRole("button", { name: "산출물", exact: true }).click();
  await expect(right).toBeVisible();
  await expect(left).toBeHidden();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(
    390,
  );
  expect(errors).toEqual([]);
});
