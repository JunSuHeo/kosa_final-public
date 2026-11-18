import { test, expect } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  const health = await (await request.get("/health")).json();
  expect(health.auth_mode).toBe("mock");
  expect(health.ai_mode).toBe("mock");
});

test("아이디어부터 네 산출물, 승인, 직접 편집과 버전 복원까지", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByLabel("만들고 싶은 제품 아이디어")
    .fill("브라우저 검증용 팀 일정 관리 서비스 " + Date.now());
  await page.getByRole("button", { name: "기획 시작하기" }).click();
  await expect(
    page.getByRole("heading", { name: "이 제품을 주로 누가 사용하나요?" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "AI가 가정하고 바로 진행" }).click();
  await expect(
    page.getByRole("button", { name: "초안이 준비됐어요" }),
  ).toBeVisible({ timeout: 20000 });
  await page.getByRole("tab", { name: "기능명세서" }).click();
  await expect(page.locator(".react-flow__node").first()).toBeVisible();
  await page.getByRole("button", { name: "디렉토리", exact: true }).click();
  await expect(page.locator(".feature-row")).toHaveCount(3);
  await page.getByLabel("기능 검색").fill("상세");
  await expect(page.locator(".feature-row")).toHaveCount(1);
  await page.getByRole("tab", { name: "유저플로우" }).click();
  await expect(page.locator(".react-flow__node")).toHaveCount(7);
  await page.getByRole("tab", { name: "와이어프레임" }).click();
  await expect(page.locator(".wire-thumbnail")).toHaveCount(3);
  await page.locator(".wire-thumbnail").first().click();
  await page.getByRole("button", { name: "미리보기", exact: true }).click();
  await page.locator(".wire-page .wire-button").click();
  await expect(page.locator(".wire-view-title strong")).toHaveText(
    "새 항목 작성",
  );
  await page.getByRole("button", { name: "초안이 준비됐어요" }).click();
  await page
    .getByRole("checkbox", { name: "경고와 확인이 필요한 가정을 검토했어요" })
    .check();
  await page.getByRole("button", { name: "승인하고 확정" }).click();
  await expect(
    page.getByRole("button", { name: "확정본 v1", exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "PRD", exact: true }).click();
  await page.getByRole("button", { name: "직접 편집", exact: true }).click();
  await page.getByLabel("제품 목표 편집").fill("직접 편집한 새 목표입니다.");
  await page.getByRole("button", { name: "수정안 검토", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "확정본 v1", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "검토 중인 초안" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "확정본 v1", exact: true }).click();
  await expect(
    page.locator(".prd-field").filter({ hasText: "제품 목표" }),
  ).not.toContainText("직접 편집한 새 목표입니다.");
  await page.getByRole("button", { name: "검토 중인 초안" }).click();
  await page
    .getByRole("checkbox", { name: "경고와 확인이 필요한 가정을 검토했어요" })
    .check();
  await page.getByRole("button", { name: "승인하고 확정" }).click();
  await expect(
    page.getByRole("button", { name: "확정본 v2", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.locator(".prd-field").filter({ hasText: "제품 목표" }),
  ).toContainText("직접 편집한 새 목표입니다.");
  await page.getByRole("button", { name: "버전", exact: true }).click();
  await page.locator(".versions-list>button").filter({ hasText: "v1" }).click();
  await expect(page.locator(".history-badge")).toContainText("과거 버전 v1");
  await expect(
    page.locator(".prd-field").filter({ hasText: "제품 목표" }),
  ).not.toContainText("직접 편집한 새 목표입니다.");
  await page.getByRole("button", { name: "이 버전으로 복원 제안" }).click();
  await expect(
    page.getByRole("button", { name: "확정본 v2", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "거절", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "확정본 v2", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "내보내기" }).click();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "JSON (.json)", exact: true }).click();
  expect((await downloaded).suggestedFilename()).toBe("studio-v2.json");
});

test("와이어프레임 편집은 새 수정안이며 승인 전 저장된 버전을 바꾸지 않는다", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByLabel("만들고 싶은 제품 아이디어")
    .fill("모바일 동네 모임 앱 와이어프레임 검증 " + Date.now());
  await page.getByRole("button", { name: "기획 시작하기" }).click();
  await expect(
    page.getByRole("button", { name: "AI가 가정하고 바로 진행" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "AI가 가정하고 바로 진행" }).click();
  await expect(
    page.getByRole("button", { name: "초안이 준비됐어요" }),
  ).toBeVisible({ timeout: 20000 });
  await page.getByRole("button", { name: "초안이 준비됐어요" }).click();
  await page
    .getByRole("checkbox", { name: "경고와 확인이 필요한 가정을 검토했어요" })
    .check();
  await page.getByRole("button", { name: "승인하고 확정" }).click();
  await expect(
    page.getByRole("button", { name: "확정본 v1", exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "와이어프레임" }).click();
  await page.locator(".wire-thumbnail").first().click();
  await page.getByRole("button", { name: "직접 편집", exact: true }).click();
  await page
    .getByRole("button", { name: "블록 선택 오늘의 작업을 시작해 볼까요?" })
    .click();
  await page.getByLabel("요소 표시 텍스트").fill("새로운 모임을 찾아보세요");
  await page.getByRole("button", { name: "수정안 검토", exact: true }).click();
  await expect(page.locator(".wire-page h1")).toHaveText(
    "새로운 모임을 찾아보세요",
  );
  await page.getByRole("button", { name: "확정본 v1", exact: true }).click();
  await expect(page.locator(".wire-page h1")).toHaveText(
    "오늘의 작업을 시작해 볼까요?",
  );
});

test("모바일 화면에서 프로젝트와 도구 패널을 사용할 수 있다", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByLabel("만들고 싶은 제품 아이디어")).toBeVisible();
  await page
    .getByLabel("만들고 싶은 제품 아이디어")
    .fill("모바일 화면 테스트용 기획 " + Date.now());
  await page.getByRole("button", { name: "기획 시작하기" }).click();
  await expect(page.locator(".side-panel")).toBeVisible();
  await page.getByRole("button", { name: "채팅", exact: true }).click();
  await expect(page.locator(".side-panel")).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "와이어프레임" })).toBeVisible();
  await page.getByRole("button", { name: "채팅", exact: true }).click();
  await expect(page.locator(".side-panel")).toBeVisible();
  await page.getByRole("button", { name: "AI가 가정하고 바로 진행" }).click();
  await expect(
    page.getByRole("button", { name: "초안이 준비됐어요" }),
  ).toBeVisible({ timeout: 20000 });
  await page.getByRole("button", { name: "채팅", exact: true }).click();
  await page.getByRole("tab", { name: "와이어프레임" }).click();
  await page.locator(".wire-thumbnail").first().click();
  await expect(page.locator(".wire-inspector")).toHaveCount(0);
  await page
    .getByRole("button", { name: "화면 속성 패널", exact: true })
    .click();
  await expect(page.locator(".wire-inspector")).toBeVisible();
  await page.getByRole("button", { name: "속성 패널 닫기" }).click();
  await expect(page.locator(".wire-inspector")).toHaveCount(0);
});

test("다섯 역할의 근거·수정 제안·검수 기준을 보고 원문으로 이동한다", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("만들고 싶은 제품 아이디어").fill("역할별 검토 확인용 팀 업무 서비스 " + Date.now());
  await page.getByRole("button", { name: "기획 시작하기" }).click();
  await page.getByRole("button", { name: "AI가 가정하고 바로 진행" }).click();
  await page.getByRole("button", { name: "초안이 준비됐어요" }).click();
  await page.getByRole("button", { name: "역할별 AI 검토", exact: true }).click();
  await expect(page.getByRole("group", { name: "검토 역할" }).getByRole("button")).toHaveCount(5);
  await page.getByRole("button", { name: "다섯 역할 검토 시작" }).click();
  await expect(page.locator(".role-progress")).toContainText("5/5 역할 완료", { timeout: 20000 });
  for (const name of ["개발자", "기획자", "보안", "UI/UX", "QA"]) {
    await page.getByRole("group", { name: "검토 역할" }).getByRole("button", { name: new RegExp(name.replace("/", "\\/") + " 완료") }).click();
    await expect(page.locator(".role-summary")).toContainText(name);
    await expect(page.locator(".role-finding")).toContainText("수정 제안");
    await expect(page.locator(".role-finding")).toContainText("수정 후 확인");
  }
  await page.locator(".finding-evidence").first().click();
  await expect(page.getByRole("tab", { name: "PRD", exact: true })).toHaveAttribute("aria-selected", "true");
  const projectId = new URL(page.url()).searchParams.get("project");
  const result = await (await page.request.get(`/api/projects/${projectId}`, { headers: { Authorization: "Bearer local:demo-user" } })).json();
  expect(result.project.current_version).toBe(0);
  expect(result.proposal).not.toBeNull();
  await page.reload();
  await page.getByRole("button", { name: "검토", exact: true }).click();
  await page.getByRole("button", { name: "역할별 AI 검토", exact: true }).click();
  await expect(page.locator(".role-progress")).toContainText("5/5 역할 완료");
});
