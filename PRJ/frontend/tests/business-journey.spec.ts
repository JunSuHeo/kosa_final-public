import { test, expect, headers } from "./server-fixture";
import { begin, businessSource, confirm, draft, login, readBundle } from "./business-helpers";

test.beforeEach(async ({ page }) => { await login(page); });

test("업무 한 번 선택으로 대화를 열고 첫 설명과 선택 유형을 새로고침 후 복원한다", async ({ page }) => {
  const source = await businessSource(page.request);
  await page.goto("/");
  await page.locator(`.business-card[data-source-id="${source.id}"]`).click();
  await expect(page.getByLabel("업무 설명", { exact: true })).toBeVisible();
  await page.getByLabel("업무 설명", { exact: true }).fill("발주 반려 사유 확인 과정을 개선하고 싶어요.");
  await page.getByLabel("기획 유형 (선택)").selectOption("process");
  await page.reload();
  await expect(page.getByLabel("업무 설명", { exact: true })).toHaveValue("발주 반려 사유 확인 과정을 개선하고 싶어요.");
  await expect(page.getByLabel("기획 유형 (선택)")).toHaveValue("process");
});

test("보내지 않은 대화를 보존하고 초안 생성을 막으며 한글 조합 Enter를 전송하지 않는다", async ({ page }) => {
  const id = await begin(page);
  const input = page.getByLabel("업무 대화 입력", { exact: true });
  const text = "승인자가 반려 이유를 남기도록 해 주세요.";
  await input.fill(text);
  await expect(page.locator(".draft-action")).toBeDisabled();
  await expect(page.getByText("입력한 내용을 먼저 보내면 초안에 반영할 수 있어요.", { exact: true })).toBeVisible();
  await page.reload();
  await expect(input).toHaveValue(text);
  const before = await readBundle(page, id);
  await input.dispatchEvent("compositionstart");
  await input.dispatchEvent("keydown", { key: "Enter", code: "Enter", isComposing: true, keyCode: 229 });
  await input.dispatchEvent("compositionend");
  await expect(input).toHaveValue(text);
  expect((await readBundle(page, id)).messages.length).toBe(before.messages.length);
  await input.press("Enter");
  await expect(input).toHaveValue("");
  await expect(page.locator(".draft-action")).toBeEnabled();
  await page.reload();
  await expect(input).toHaveValue("");
});

test("현재 확인 질문을 한 번 표시하고 직접 답변 초안을 보존하며 미정 답변도 보낸다", async ({ page }) => {
  const id = await begin(page);
  const bundle = await readBundle(page, id);
  const question = bundle.job.partial.discussion.questions[0];
  const card = page.locator(".dialogue-question").first();
  await expect(page.getByText(question.title, { exact: true })).toHaveCount(1);
  await expect(page.locator(".message.assistant").last()).not.toContainText(question.title);
  await card.getByRole("button", { name: "직접 입력", exact: true }).click();
  await card.getByLabel("질문 직접 답변").fill("발주 승인 팀은 아직 확인하고 있어요.");
  await page.reload();
  await expect(card.getByLabel("질문 직접 답변")).toHaveValue("발주 승인 팀은 아직 확인하고 있어요.");
  await card.getByRole("button", { name: "아직 미정이에요", exact: true }).click();
  await card.getByRole("button", { name: "답변 보내기", exact: true }).click();
  await expect.poll(async () => (await readBundle(page, id)).messages.some((m: { role: string; content: string }) => m.role === "user" && m.content.includes("답변: 아직 미정이에요"))).toBe(true);
});

test("모바일에서 입력·초안 생성이 화면 안에 있고 수정안은 이전과 이번 업무 내용을 보여준다", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const id = await begin(page);
  await expect(page.getByRole("tab")).toHaveCount(0);
  await expect(page.getByLabel("업무 대화 입력")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await draft(page);
  await confirm(page);
  const before = await readBundle(page, id);
  const snapshot = structuredClone(before.revision.snapshot);
  const original = snapshot.features[0].description;
  snapshot.features[0].description = "팀장이 반려 사유를 확인한 뒤 재승인합니다.";
  const response = await page.request.post(`/api/projects/${id}/proposals`, { headers, data: { base_version: 1, snapshot } });
  expect(response.ok()).toBeTruthy();
  await page.reload();
  await page.getByLabel("기획 도구").selectOption("review");
  const comparison = page.locator(".review-change-row").filter({ hasText: "팀장이 반려 사유" });
  await expect(comparison).toContainText(original);
  await expect(comparison).toContainText("이전 업무");
  await expect(comparison).toContainText("이번 업무");
});
