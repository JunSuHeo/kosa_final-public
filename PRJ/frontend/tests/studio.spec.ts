import { login } from "./business-helpers";
import { test, expect } from "./server-fixture";
test.beforeEach(async ({ page }) => {
  await login(page);
});
import {
  begin,
  businessSource,
  confirm,
  draft,
  readBundle,
} from "./business-helpers";

test.beforeEach(async ({ request }) => {
  const health = await (await request.get("/health")).json();
  expect(health.auth_mode).toBe("supabase");
  expect(health.ai_mode).toBe("mock");
});

test("업무 선택과 대화 후 명시적으로 초안을 만들고 확인본·편집·복원을 이어간다", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const id = await begin(page);
  expect((await readBundle(page, id)).proposal).toBeNull();
  await expect(page.getByRole("tab")).toHaveCount(0);
  await page
    .getByLabel("업무 대화 입력")
    .fill("현업 담당자가 요청하고 팀장이 승인해요.");
  await page.getByRole("button", { name: "업무 대화 보내기" }).click();
  await expect(page.locator(".draft-action")).toBeEnabled();
  await draft(page);
  await page.getByRole("tab", { name: "기능 상세", exact: true }).click();
  await expect(page.locator(".feature-article")).toHaveCount(3);
  await expect(
    page.getByRole("button", { name: "그래프", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("tab", { name: "업무 흐름", exact: true }).click();
  await expect(page.locator(".react-flow__node")).toHaveCount(7);
  await page.getByRole("tab", { name: "화면 시안", exact: true }).click();
  await expect(page.locator(".wire-thumbnail")).toHaveCount(3);
  await page.locator(".wire-thumbnail").first().click();
  await page.getByRole("button", { name: "미리보기", exact: true }).click();
  await page.locator(".wire-page .wire-button").click();
  await expect(page.locator(".wire-view-title strong")).toHaveText(
    "새 항목 작성",
  );
  await confirm(page);
  await expect(
    page.getByRole("button", { name: "현업 확인본 v1", exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "기획 내용", exact: true }).click();
  await page.getByRole("button", { name: "직접 편집", exact: true }).click();
  await page.getByLabel("제품 목표 편집").fill("직접 편집한 업무 목표입니다.");
  await page
    .getByRole("button", { name: "수정 내용 확인", exact: true })
    .click();
  expect((await readBundle(page, id)).project.current_version).toBe(1);
  await page
    .getByRole("checkbox", { name: "위 확인 사항과 가정을 살펴봤어요" })
    .check();
  await page
    .getByRole("button", { name: "현업 확인본 저장", exact: true })
    .click();
  await page.reload();
  await expect(
    page.locator(".prd-field").filter({ hasText: "제품 목표" }),
  ).toContainText("직접 편집한 업무 목표입니다.");
  await page.getByRole("button", { name: "기록", exact: true }).click();
  await page.locator(".versions-list>button").filter({ hasText: "v1" }).click();
  await expect(page.locator(".history-badge")).toContainText("과거 버전 v1");
  await page.getByRole("button", { name: "이 버전으로 복원 제안" }).click();
  await page
    .getByRole("button", { name: "이 초안 사용 안 함", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "현업 확인본 v2", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "내보내기" }).click();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "기획 데이터 (.json)", exact: true }).click();
  expect((await downloaded).suggestedFilename()).toBe("studio-v2.json");
  expect(errors).toEqual([]);
});

test("미확정 시안의 요소를 대화에 붙여 수정하고 최초 초안을 거절해도 계속 대화한다", async ({
  page,
}) => {
  const id = await begin(page);
  await draft(page);
  const before = await readBundle(page, id);
  await page.getByRole("tab", { name: "화면 시안", exact: true }).click();
  await page.locator(".wire-thumbnail").first().click();
  const heading = page.locator(".wire-page .wire-heading");
  await heading.click();
  await expect(page.locator(".mention")).toContainText("선택한 항목 수정하기");
  await page.getByLabel("업무 대화 입력").fill("발주 승인 현황");
  await page.getByRole("button", { name: "업무 대화 보내기" }).click();
  await expect(page.locator(".draft-action")).toBeEnabled();
  await page.locator(".draft-action").click();
  await expect(heading).toContainText("발주 승인 현황");
  await expect(heading).toHaveClass(/block-changed/);
  const after = await readBundle(page, id);
  expect(after.proposal.id).not.toBe(before.proposal.id);
  expect(after.project.current_version).toBe(0);
  await page.locator(".review-chat-card").click();
  await page
    .getByRole("button", { name: "이 초안 사용 안 함", exact: true })
    .click();
  await page.getByRole("button", { name: "업무 대화", exact: true }).click();
  await page
    .getByLabel("업무 대화 입력")
    .fill("예외 처리 기준부터 다시 정리할게요.");
  const discussed = page.waitForResponse(response =>
    response.request().method() === "POST" && response.url().endsWith("/jobs") &&
    response.request().postDataJSON()?.kind === "discuss");
  await page.getByRole("button", { name: "업무 대화 보내기" }).click();
  const discussion = await (await discussed).json();
  await expect.poll(async () => {
    const job = (await readBundle(page, id)).job;
    return job.id === discussion.id && job.status === "completed";
  }).toBeTruthy();
  await expect(page.locator(".draft-action")).toBeEnabled();
  await draft(page);
  expect((await readBundle(page, id)).proposal).not.toBeNull();
});

test("모바일 대화·산출물 전환과 화면 요소 선택이 가능하다", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await begin(page);
  await draft(page);
  await expect(page.locator(".side-panel")).toBeVisible();
  await page.getByRole("button", { name: "산출물", exact: true }).click();
  await expect(page.locator(".side-panel")).toBeHidden();
  await page.getByRole("tab", { name: "화면 시안", exact: true }).click();
  await page.locator(".wire-thumbnail").first().click();
  await expect(page.locator(".wire-inspector")).toHaveCount(0);
  await page
    .getByRole("button", { name: "화면 속성 패널", exact: true })
    .click();
  await expect(page.locator(".wire-inspector")).toBeVisible();
  await page.getByRole("button", { name: "속성 패널 닫기" }).click();
  await page.locator(".wire-page .wire-heading").click();
  await page.getByRole("button", { name: "대화", exact: true }).click();
  await expect(page.locator(".mention")).toContainText("선택한 항목 수정하기");
  const widths = await page.evaluate(() => [
    document.documentElement.scrollWidth,
    window.innerWidth,
  ]);
  expect(widths[0]).toBe(widths[1]);
  await page.screenshot({
    path: "test-results/hplan-mobile.png",
    fullPage: true,
  });
});

test("기존 역할 검토는 IT 상세에서 실행하고 같은 기획 원문으로 이동한다", async ({
  page,
}) => {
  const id = await begin(page);
  await draft(page);
  await page.locator(".review-chat-card").click();
  await page.getByRole("button", { name: "IT 상세 검토", exact: true }).click();
  await page.getByRole("button", { name: "다섯 역할 검토 시작" }).click();
  await expect(page.locator(".role-progress")).toContainText("5/5 역할 완료", {
    timeout: 20000,
  });
  await page.locator(".finding-evidence").first().click();
  await expect(
    page.getByRole("tab", { name: "기획 내용", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  expect((await readBundle(page, id)).project.current_version).toBe(0);
});

test("밝은 홈은 긴 업무명과 기획명에서도 가로로 넘치지 않는다", async ({
  page,
}) => {
  const source = await businessSource(page.request);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/sources", (route) =>
    route.fulfill({
      json: [
        {
          ...source,
          name: "긴업무이름".repeat(20),
          description: "현업의 업무를 설명하는 내용".repeat(20),
        },
      ],
    }),
  );
  await page.goto("/");
  await expect(page.locator(".business-card")).toBeVisible();
  await expect(page.getByLabel("만들고 싶은 제품 아이디어")).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(
    390,
  );
  await expect(page.locator("body")).toHaveCSS(
    "background-color",
    "rgb(245, 247, 251)",
  );
});

test("질문 카드의 선택지와 직접 입력으로 대화하고 초안은 별도로 만든다", async ({
  page,
}) => {
  const id = await begin(page);
  const card = page.getByLabel("업무 확인 질문", { exact: true });
  await expect(card).toBeVisible();
  await expect(card).toContainText("이 업무의 확인과 승인은 누가 하나요?");
  await expect(
    card.getByRole("button", { name: "답변 보내기", exact: true }),
  ).toBeDisabled();
  await page.reload();
  await expect(card).toBeVisible();
  await card
    .getByRole("button", {
      name: "담당자가 요청하고 팀장이 승인해요",
      exact: true,
    })
    .click();
  await card.getByRole("button", { name: "답변 보내기", exact: true }).click();
  await expect(card).toContainText("예외가 발생하면 어떻게 처리할까요?");
  let bundle = await readBundle(page, id);
  expect(bundle.proposal).toBeNull();
  expect(
    bundle.messages.filter((m: { role: string }) => m.role === "user").at(-1)
      .content,
  ).toContain("답변: 담당자가 요청하고 팀장이 승인해요");
  await card.getByRole("button", { name: "직접 입력", exact: true }).click();
  await card
    .getByLabel("질문 직접 답변")
    .fill("반려 사유를 입력하고 발주 담당자가 보완 후 다시 요청해요.");
  await card.getByRole("button", { name: "답변 보내기", exact: true }).click();
  await expect(page.locator(".draft-action")).toBeEnabled();
  bundle = await readBundle(page, id);
  expect(bundle.proposal).toBeNull();
  expect(bundle.project.conversation_brief.user_statements.at(-1)).toContain(
    "발주 담당자가 보완",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(card).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(
    390,
  );
  await draft(page);
  expect((await readBundle(page, id)).proposal).not.toBeNull();
});
