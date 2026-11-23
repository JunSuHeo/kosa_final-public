import { expect, test, headers, loginHeaders } from "./server-fixture";
import type { Page } from "@playwright/test";
import { businessSource, login } from "./business-helpers";
const password = "a123456789!";

async function menu(page: Page, name: string) {
  await page
    .getByRole("button", { name: "관리자 메뉴 열기", exact: true })
    .filter({ visible: true })
    .click();
  await page
    .getByRole("navigation", { name: "관리자 메뉴", exact: true })
    .getByRole("button", { name, exact: true })
    .click();
}
async function logout(page: Page) {
  await page
    .getByLabel("계정 메뉴", { exact: true })
    .filter({ visible: true })
    .click();
  await page.getByRole("button", { name: "로그아웃", exact: true }).click();
  await expect(
    page.getByRole("form", { name: "로그인", exact: true }),
  ).toBeVisible();
}
async function manage(page: Page, id: string) {
  await page.getByRole("button", { name: `${id} 관리`, exact: true }).click();
  return page.getByRole("region", { name: "계정 상세", exact: true });
}

test("세 계정의 역할·세션과 관리자 주소 접근 제한", async ({ page }) => {
  for (const [id, role] of [
    ["user1", "USER1"],
    ["user2", "USER2"],
  ]) {
    await login(page, "/?view=accounts", id);
    await expect(page).toHaveURL(/\/$/);
    await expect(
      page.getByRole("button", { name: "관리자 메뉴 열기" }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("heading", { name: "계정 관리", exact: true }),
    ).toHaveCount(0);
    await page.getByLabel("계정 메뉴", { exact: true }).click();
    await expect(page.locator(".account-popover")).toContainText(role);
    await page.keyboard.press("Escape");
    await page.reload();
    await expect(
      page.getByRole("heading", { name: "어떤 업무를 기획하시겠어요?" }),
    ).toBeVisible();
    await page.goto("/?view=settings");
    await expect(page).toHaveURL(/\/$/);
    await expect(
      page.getByRole("heading", { name: "업무 연결 설정", exact: true }),
    ).toHaveCount(0);
    await logout(page);
  }
  await login(page);
  await menu(page, "계정 관리");
  await expect(
    page.getByRole("heading", { name: "계정 관리", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/hplan-accounts-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  const toggle = page.getByRole("button", {
    name: "관리자 메뉴 열기",
    exact: true,
  });
  await toggle.click();
  const drawer = page.getByRole("dialog", { name: "관리자 내비게이션" });
  await expect(drawer).toBeVisible();
  await page.screenshot({
    path: "test-results/hplan-admin-mobile.png",
    fullPage: true,
  });
  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
  await expect(toggle).toBeFocused();
  await toggle.click();
  await page.mouse.click(380, 600);
  await expect(drawer).toHaveCount(0);
  await toggle.click();
  await page.getByRole("button", { name: "내비게이션 닫기" }).click();
  await expect(drawer).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(
    390,
  );
});

test("브라우저 계정 변조는 서버 권한을 바꾸지 않고 새 브라우저도 DB 계정을 사용한다", async ({ page, browser, request }) => {
  await page.addInitScript(() => {
    localStorage.setItem("hplan-accounts.v1", JSON.stringify({ accounts: [{ loginId: "user1", role: "ADMINISTRATOR" }] }));
    sessionStorage.setItem("hplan-session.v2", JSON.stringify({ accountId: "demo-user", version: 1 }));
    sessionStorage.setItem("studio-token", "local:demo-user");
  });
  await login(page, "/?view=accounts", "user1");
  await expect(page.getByRole("button", { name: "관리자 메뉴 열기" })).toHaveCount(0);
  expect(await page.evaluate(() => localStorage.getItem("hplan-accounts.v1"))).toBeNull();
  const userHeaders = await loginHeaders(request, "user1");
  expect((await request.get("/api/accounts", { headers: userHeaders })).status()).toBe(403);
  expect((await request.get("/api/accounts", { headers: { Authorization: "Bearer local:demo-user" } })).status()).toBe(401);
  const fresh = await browser.newContext({ baseURL: process.env.E2E_BASE_URL });
  try {
    const other = await fresh.newPage();
    await login(other, "/", "user2");
    await other.getByLabel("계정 메뉴", { exact: true }).click();
    await expect(other.locator(".account-popover")).toContainText("USER2");
  } finally { await fresh.close(); }
});

test("계정 등록·수정·필터·마지막 관리자 보호·변경 이력", async ({ page }) => {
  await login(page);
  await menu(page, "계정 관리");
  let detail = await manage(page, "admin");
  await detail.getByLabel("역할", { exact: true }).selectOption("USER1");
  await detail.getByRole("button", { name: "계정 정보 저장" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "마지막 활성 ADMINISTRATOR",
  );
  await detail
    .getByLabel("역할", { exact: true })
    .selectOption("ADMINISTRATOR");
  await detail.getByLabel("사용 상태", { exact: true }).selectOption("false");
  await detail.getByRole("button", { name: "계정 정보 저장" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "마지막 활성 ADMINISTRATOR",
  );
  await page.getByRole("button", { name: "계정 등록", exact: true }).click();
  detail = page.getByRole("region", { name: "계정 상세" });
  await detail.getByLabel("로그인 ID").fill("planner3");
  await detail.getByLabel("표시 이름").fill("업무 담당자");
  await detail.getByLabel("초기 비밀번호", { exact: true }).fill(password);
  await detail.getByRole("button", { name: "등록하기" }).click();
  await expect(page.getByRole("status")).toContainText("계정을 등록했습니다");
  await expect(detail.getByLabel("로그인 ID")).toBeDisabled();
  await detail.getByLabel("표시 이름").fill("수정한 담당자");
  await detail.getByRole("button", { name: "계정 정보 저장" }).click();
  await expect(page.getByRole("region", { name: "계정 목록" })).toContainText(
    "수정한 담당자",
  );
  await page.getByLabel("계정 검색").fill("planner3");
  await expect(
    page.getByRole("button", { name: "user1 관리", exact: true }),
  ).toHaveCount(0);
  await page.getByLabel("역할 필터").selectOption("USER2");
  await expect(page.getByText("검색한 계정이 없습니다.")).toBeVisible();
  await page.getByLabel("역할 필터").selectOption("USER1");
  await expect(
    page.getByRole("button", { name: "planner3 관리", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByRole("region", { name: "계정 목록" })).toContainText(
    "수정한 담당자",
  );
  await menu(page, "변경 이력");
  await expect(page.locator("main")).toContainText("계정 등록");
  await expect(page.locator("main")).toContainText("정보 변경");
  await expect(page.locator("main")).toContainText("로그인");
  await expect(page.locator("main")).not.toContainText(password);
  const createdUser = await page.context().newPage();
  await login(createdUser, "/", "planner3");
  await expect(createdUser.locator(".project-card")).toHaveCount(0);
  await createdUser.close();
  expect(await page.evaluate(() => localStorage.getItem("hplan-accounts.v1"))).toBeNull();
  const storage = await page.evaluate(() =>
    JSON.stringify({ ...localStorage, ...sessionStorage }),
  );
  expect(storage).not.toContain(password);
  expect(await page.evaluate(() => sessionStorage.getItem("hplan-session.v2"))).toBeNull();
  expect(await page.evaluate(() => !!JSON.parse(sessionStorage.getItem("hplan-supabase-session.v1")!).access_token)).toBeTruthy();
});

test("다른 탭의 역할·비밀번호·사용 상태 변경은 세션을 종료하고 권한 정책은 즉시 반영", async ({
  page,
  context,
}) => {
  const source = await businessSource(page.request);
  await login(page);
  await menu(page, "계정 관리");
  const user = await context.newPage();
  await login(user, "/", "user1");
  let detail = await manage(page, "user1");
  await detail.locator(`[data-source-id="${source.id}"] input[type="checkbox"]`).check();
  await detail.getByLabel("역할", { exact: true }).selectOption("USER2");
  await detail.getByRole("button", { name: "계정 정보 저장" }).click();
  await expect(
    user.getByRole("form", { name: "로그인", exact: true }),
  ).toBeVisible();
  await login(user, "/", "user1");
  await user.getByLabel("계정 메뉴", { exact: true }).click();
  await expect(user.locator(".account-popover")).toContainText("USER2");
  await user.keyboard.press("Escape");
  await detail.getByLabel("새 비밀번호", { exact: true }).fill("changed12345!");
  await detail
    .getByRole("button", { name: "비밀번호 재설정", exact: true })
    .click();
  await expect(
    user.getByRole("form", { name: "로그인", exact: true }),
  ).toBeVisible();
  await user.getByLabel("아이디", { exact: true }).fill("user1");
  await user.getByLabel("비밀번호", { exact: true }).fill(password);
  await user.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(user.getByRole("alert")).toContainText("ID 또는 비밀번호");
  await login(user, "/", "user1", "changed12345!");
  await detail.getByLabel("사용 상태", { exact: true }).selectOption("false");
  await detail.getByRole("button", { name: "계정 정보 저장" }).click();
  await expect(
    user.getByRole("form", { name: "로그인", exact: true }),
  ).toBeVisible();
  await detail.getByLabel("사용 상태", { exact: true }).selectOption("true");
  await detail.getByRole("button", { name: "계정 정보 저장" }).click();
  await login(user, "/", "user1", "changed12345!");
  expect(await user.evaluate(() => sessionStorage.getItem("hplan-session.v2"))).toBeNull();
  await menu(page, "역할·권한 설정");
  await page.getByLabel("USER2 기획 작성", { exact: true }).uncheck();
  await expect(
    user.locator(".business-card").first(),
  ).toBeDisabled();
  await user.goto("/?view=intake");
  await expect(user).toHaveURL(/\/$/);
  await user.reload();
  await expect(
    user.locator(".business-card").first(),
  ).toBeDisabled();
  await expect(
    page.getByLabel("USER1 계정 관리", { exact: true }),
  ).toBeDisabled();
});

test("업무 배정으로 같은 업무의 기획을 분리하고 배정 해제 후 문서를 보존", async ({
  page,
  context,
  request,
}) => {
  const source = await businessSource(request);
  await login(page);
  await menu(page, "계정 관리");
  for (const id of ["user1", "user2"]) {
    const detail = await manage(page, id);
    const assignment = detail.locator(
      `[data-source-id="${source.id}"] input[type="checkbox"]`,
    );
    await expect(assignment).toBeVisible();
    await assignment.check();
  }
  const plans: Record<string, string> = {};
  const user = await context.newPage();
  for (const id of ["user1", "user2"]) {
    await login(user, "/", id);
    await user.locator(`[data-source-id="${source.id}"]`).click();
    await user
      .getByLabel("업무 설명", { exact: true })
      .fill(`${id}의 발주 승인 업무를 개선합니다 ${Date.now()}`);
    await user
      .getByRole("button", { name: "업무 대화 시작", exact: true })
      .click();
    await expect(user).toHaveURL(/project=/);
    plans[id] = new URL(user.url()).searchParams.get("project")!;
    await expect(user.locator(".draft-action")).toBeEnabled();
    if (id === "user1") {
      await user.locator(".draft-action").click();
      await expect(user.locator(".review-chat-card")).toBeVisible();
      await user.locator(".review-chat-card").click();
      const ack = user.getByRole("checkbox", {
        name: "위 확인 사항과 가정을 살펴봤어요",
      });
      if (await ack.count()) await ack.check();
      await user
        .getByRole("button", { name: "현업 확인본 저장", exact: true })
        .click();
      await expect(
        user.getByRole("button", { name: "현업 확인본 저장", exact: true }),
      ).toHaveCount(0);
    }
    const own = await (
      await request.get("/api/projects", {
        headers: await loginHeaders(request, id),
      })
    ).json();
    expect(own.some((p: { id: string }) => p.id === plans[id])).toBeTruthy();
    await logout(user);
  }
  expect(
    (
      await request.get(`/api/projects/${plans.user1}`, {
        headers: await loginHeaders(request, "user2"),
      })
    ).status(),
  ).toBe(404);
  expect(
    (await request.get(`/api/projects/${plans.user1}`, { headers })).status(),
  ).toBe(404);
  const detail = await manage(page, "user1");
  await detail
    .locator(`[data-source-id="${source.id}"] input[type="checkbox"]`)
    .uncheck();
  await login(user, `/?project=${plans.user1}`, "user1");
  await expect(user.getByText(/업무 배정이 해제되어/)).toBeVisible();
  await expect(user.locator(".draft-action")).toBeDisabled();
  expect(
    (
      await request.get(
        `/api/projects/${plans.user1}/revisions/1/export?format=json`,
        { headers: await loginHeaders(request, "user1") },
      )
    ).ok(),
  ).toBeTruthy();
  await user.setViewportSize({ width: 390, height: 844 });
  await expect(user.getByLabel("기획 도구")).toBeVisible();
});

test("업무 권한을 위임받은 역할은 본인 게시 업무만 배정하고 계정 관리에는 접근하지 못한다", async ({ page, context, request }) => {
  await login(page);
  await menu(page, "역할·권한 설정");
  await page.getByLabel("USER1 업무 연결 준비", { exact: true }).check();
  await page.getByLabel("USER1 업무 배정", { exact: true }).check();
  await expect(page.getByRole("status")).toContainText("권한을 변경했습니다");
  const ownerHeaders = await loginHeaders(request, "user1");
  const result = await request.post("/api/sources", { headers: ownerHeaders, data: {
    name: "담당자 소유 업무", description: "권한 위임과 업무 소유권을 확인합니다.", kind: "local", repository: process.env.E2E_FIXTURE_REPO, ref: "HEAD",
  } });
  expect(result.ok()).toBeTruthy();
  const source = await result.json();
  const snapshot = await (await request.post(`/api/sources/${source.id}/analyze`, {headers:ownerHeaders,data:{}})).json();
  await expect.poll(async () => (await (await request.get(`/api/sources/${source.id}/snapshots/${snapshot.id}`, {headers:ownerHeaders})).json()).status).toBe("ready");
  const preview = await (await request.post(`/api/sources/${source.id}/snapshots/${snapshot.id}/publication-preview`, {headers:ownerHeaders,data:{}})).json();
  expect((await request.post(`/api/sources/${source.id}/publish`, {headers:ownerHeaders,data:{snapshot_id:snapshot.id,fingerprint:preview.fingerprint,design_profile:preview.design_profile}})).ok()).toBeTruthy();
  const user = await context.newPage(); await login(user,"/","user1");
  const header = user.locator(".business-home .business-header");
  const settings = header.getByRole("button", {
    name: "업무 연결 설정",
    exact: true,
    includeHidden: true,
  });
  for (const viewport of [{ width: 390, height: 844 }, { width: 1440, height: 1000 }]) {
    await user.setViewportSize(viewport);
    await expect(header).toBeVisible();
    await expect(settings).toHaveCount(0);
  }
  await expect(user.getByRole("button",{name:"관리자 메뉴 열기"})).toHaveCount(0);
  await user.goto("/?view=settings");
  await expect(
    user.getByRole("heading", { name: "업무 연결 설정", exact: true }),
  ).toBeVisible();
  await user.getByRole("button",{name:"업무 배정",exact:true}).click();
  await expect(user.getByRole("heading",{name:"업무 배정",exact:true})).toBeVisible();
  await user.getByLabel("배정할 업무",{exact:true}).selectOption(source.id);
  await user.getByRole("checkbox",{name:"user2 업무 배정",exact:true}).check();
  await expect(user.getByRole("status")).toContainText("user2 계정의 업무 배정을 추가");
  expect((await request.get(`/api/sources/${source.id}/assignments`,{headers})).status()).toBe(404);
  await page.getByLabel("USER1 업무 배정",{exact:true}).uncheck();
  await expect(user).toHaveURL(/\/$/);
  await expect(user.getByRole("heading",{name:"업무 배정",exact:true})).toHaveCount(0);
  await user.goto("/?view=accounts"); await expect(user).toHaveURL(/\/$/);
});
