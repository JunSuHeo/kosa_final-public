import { login } from "./business-helpers";
import { test, expect } from "./server-fixture";
test.beforeEach(async ({ page }) => {
  await login(page);
});
import { begin, draft, confirm, readBundle } from "./business-helpers";
import { headers } from "./server-fixture";

test.beforeEach(async ({ request }) => {
  const health = await (await request.get("/health")).json();
  test.skip(
    health.ai_mode !== "mock" || health.auth_mode !== "supabase",
    "isolated mock flow",
  );
});

test("초안 문서로 이동·강조하고 수정 대화와 확인본 저장을 이어간다", async ({
  page,
}) => {
  const id = await begin(page);
  await page.getByRole("button", { name: "내용 확인", exact: true }).click();
  await expect(page.locator(".side-empty")).toContainText(
    "아직 확인할 문서가 없어요",
  );
  await page
    .getByRole("button", { name: "업무 대화로 이동", exact: true })
    .click();
  await draft(page);
  const before = await readBundle(page, id);
  await page
    .getByRole("button", { name: "아직 확인본이 없어요", exact: true })
    .click();
  await page.getByRole("button", { name: "내용 확인", exact: true }).click();
  await expect(
    page.getByRole("tab", { name: "기획 내용", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await expect(
    page
      .locator(".snapshot-switch")
      .getByRole("button", { name: "작성 중인 초안" }),
  ).toHaveClass(/active/);
  await expect(page.locator(".business-review")).toContainText(
    "이번에 정리한 업무",
  );
  await expect(page.locator(".review-guide > h4")).toHaveText([
    "1기획 내용",
    "2담당자·처리 순서·업무 규칙",
    "3업무 흐름",
    "4화면 시안",
  ]);
  await expect(page.locator(".review-diff")).not.toHaveAttribute("open", "");
  await expect(page.locator(".diff-counts")).toBeHidden();
  await page
    .locator(".review-guide")
    .first()
    .getByText("문서에 담긴 내용", { exact: true })
    .click();
  const item = page.locator(".review-document-item").first();
  const section = before.proposal.candidate.prd.sections[0];
  await item.getByRole("button", { name: "내용 보기", exact: true }).click();
  await expect(page.locator(".prd-field.review-focused")).toContainText(
    section.title,
  );
  await expect(page.locator(".prd-group").first()).toHaveCSS(
    "background-color",
    "rgb(255, 255, 255)",
  );
  await expect(page.locator(".prd-field.review-focused p")).toHaveCSS(
    "color",
    "rgb(51, 65, 85)",
  );
  await item
    .getByRole("button", { name: "이 내용 수정하기", exact: true })
    .click();
  await expect(page.locator(".mention")).toContainText(section.title);
  await page
    .getByLabel("업무 대화 입력")
    .fill("현업 담당자가 반려 사유를 확인한 후 보완하도록 해 주세요.");
  await page
    .getByRole("button", { name: "업무 대화 보내기", exact: true })
    .click();
  await expect(page.locator(".draft-action")).toBeEnabled();
  expect((await readBundle(page, id)).proposal.id).toBe(before.proposal.id);
  await draft(page);
  await confirm(page);
  await expect(page.locator(".business-review")).toContainText(
    "마지막으로 저장한 업무 내용이에요",
  );
  await expect(
    page.getByRole("button", { name: "현업 확인본 저장", exact: true }),
  ).toHaveCount(0);
  await expect
    .poll(async () => (await readBundle(page, id)).project.current_version)
    .toBe(1);
  await page.screenshot({
    path: "test-results/hplan-document-review.png",
    fullPage: true,
  });
});

test("수정안과 삭제 내용을 마지막 확인본과 비교하고 모바일 문서에서 안내로 돌아간다", async ({
  page,
}) => {
  const id = await begin(page);
  await draft(page);
  await confirm(page);
  const before = await readBundle(page, id);
  const snapshot = structuredClone(before.revision.snapshot);
  const removed = snapshot.prd.sections.pop();
  snapshot.prd.sections[0].content =
    "담당자가 발주 반려 이유를 확인하고 보완 후 다시 요청합니다.";
  const response = await page.request.post(`/api/projects/${id}/proposals`, {
    headers,
    data: { base_version: 1, snapshot },
  });
  expect(response.ok()).toBeTruthy();
  await page.reload();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByLabel("기획 도구").selectOption("review");
  await expect(page.locator(".review-changed")).toContainText(
    "마지막 확인본에서 달라진 내용",
  );
  await expect(page.locator(".review-changed")).toContainText(removed.title);
  await expect(
    page.locator(".issue.warning").filter({ hasText: "기존 내용 중" }),
  ).toContainText(removed.content);
  await page
    .locator(".review-guide")
    .first()
    .getByRole("button", { name: "내용 보기", exact: true })
    .first()
    .click();
  await expect(page.locator(".side-panel")).toBeHidden();
  await expect(page.locator(".prd-field.review-focused")).toContainText(
    "담당자가 발주 반려 이유",
  );
  await page
    .getByRole("button", { name: "확인 안내로 돌아가기", exact: true })
    .click();
  await expect(page.locator(".side-panel")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(
    390,
  );
  await page.screenshot({
    path: "test-results/hplan-review-mobile.png",
    fullPage: true,
  });
  await page
    .getByRole("checkbox", { name: "위 확인 사항과 가정을 살펴봤어요" })
    .check();
  await page
    .getByRole("button", { name: "현업 확인본 저장", exact: true })
    .click();
  await expect
    .poll(async () => (await readBundle(page, id)).project.current_version)
    .toBe(2);
});

test("연결 오류는 기술 원문 대신 해결 행동을 안내하고 실패해도 초안을 보존한다", async ({
  page,
}) => {
  const id = await begin(page);
  await draft(page);
  const before = await readBundle(page, id);
  const snapshot = structuredClone(before.proposal.candidate);
  snapshot.screens[0].blocks.find(
    (b: { type: string }) => b.type === "button",
  ).target_screen_id = "missing-screen";
  const response = await page.request.post(`/api/projects/${id}/proposals`, {
    headers,
    data: { base_version: 0, base_proposal_id: before.proposal.id, snapshot },
  });
  expect(response.ok()).toBeTruthy();
  await page.reload();
  await page.getByRole("button", { name: "내용 확인", exact: true }).click();
  await expect(page.locator(".review-blockers")).toContainText(
    "저장 전에 정리가 필요해요",
  );
  await expect(page.locator(".business-review")).not.toContainText(
    "이동 대상 와이어프레임이 없습니다",
  );
  await page.getByRole("button", { name: "IT 상세 검토", exact: true }).click();
  await page.getByText("시스템 검사 상세", { exact: true }).click();
  await expect(page.locator(".review-technical")).toContainText(
    "이동 대상 와이어프레임이 없습니다",
  );
  await page.getByRole("button", { name: "내용 확인", exact: true }).click();
  await expect(page.locator(".business-review")).toBeVisible();
  await page
    .getByRole("checkbox", { name: "위 확인 사항과 가정을 살펴봤어요" })
    .check();
  await expect(
    page.getByRole("button", { name: "현업 확인본 저장", exact: true }),
  ).toBeDisabled();
  const blocked = await readBundle(page, id);
  let releaseRepair!: () => void;
  const heldRepair = new Promise<void>((resolve) => {
    releaseRepair = resolve;
  });
  await page.route(`**/api/projects/${id}/jobs`, async (route) => {
    await heldRepair;
    await route.fulfill({
      status: 503,
      json: { detail: "일시적으로 정리 요청을 전송하지 못했어요" },
    });
  });
  await page
    .getByRole("button", { name: "AI로 정리하기", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "AI로 정리하기", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "현업 확인본 저장", exact: true }),
  ).toBeDisabled();
  releaseRepair();
  await expect(
    page.getByRole("button", { name: "AI로 정리하기", exact: true }),
  ).toBeEnabled();
  expect((await readBundle(page, id)).proposal.id).toBe(blocked.proposal.id);
  await page.unroute(`**/api/projects/${id}/jobs`);
  await page
    .getByRole("button", { name: "AI로 정리하기", exact: true })
    .click();
  await expect(page.locator(".draft-action")).toBeEnabled();
  await page.locator(".review-chat-card").click();
  await expect(page.locator(".review-blockers")).toHaveCount(0);
  expect((await readBundle(page, id)).project.current_version).toBe(0);
  await page
    .getByRole("checkbox", { name: "위 확인 사항과 가정을 살펴봤어요" })
    .check();
  await page
    .getByRole("button", { name: "현업 확인본 저장", exact: true })
    .click();
  await expect
    .poll(async () => (await readBundle(page, id)).project.current_version)
    .toBe(1);
});
