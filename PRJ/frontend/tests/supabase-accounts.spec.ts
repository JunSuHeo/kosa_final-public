import { expect, test, type Page } from "@playwright/test";
const roles = ["USER1", "USER2", "ADMINISTRATOR"] as const;
type Role = typeof roles[number];
const permissions = ["plans.read", "plans.create", "plans.edit", "plans.confirm", "plans.export", "sources.manage", "sources.assign", "accounts.manage", "roles.manage", "audit.read"];

async function authBoundary(page: Page, role: Role = "ADMINISTRATOR") {
  const policy = Object.fromEntries(roles.map(r => [r, Object.fromEntries(permissions.map(p => [p, r === "ADMINISTRATOR" || p.startsWith("plans.")]))]));
  const identity = {
    account: { id: "demo-user", loginId: "admin", name: "IT 관리자", role, active: true, sessionVersion: 1, createdAt: new Date().toISOString(), lastLoginAt: null }, policy,
  };
  let revoked = false;
  let refreshes = 0;
  const token = () => ({ access_token: "signed-test-boundary", refresh_token: "refresh-test-boundary", expires_in: 3600, identity });
  await page.route("**/health", route => route.fulfill({ json: { status: "ok", database: "ready", auth_mode: "supabase", ai_mode: "mock", provider: "openrouter", model: "fixture", version: "2.1.0" } }));
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/login") {
      const input = route.request().postDataJSON();
      if (input.identifier !== "admin" || input.password !== "test-password!")
        return route.fulfill({ status: 401, json: { detail: "ID 또는 비밀번호를 확인해 주세요" } });
      revoked = false;
      return route.fulfill({ json: token() });
    }
    if (path === "/api/auth/refresh") { refreshes++; return route.fulfill({ status: revoked ? 401 : 200, json: revoked ? { detail: "로그인 만료" } : token() }); }
    if (path === "/api/auth/logout") { revoked = true; return route.fulfill({ json: { ok: true } }); }
    if (path === "/api/auth/me") return route.fulfill({ status: revoked ? 401 : 200, json: revoked ? { detail: "다시 로그인해 주세요" } : identity });
    if (path === "/api/accounts") return route.fulfill({ json: [identity.account] });
    if (path === "/api/roles") return route.fulfill({ json: policy });
    if (path === "/api/audit") return route.fulfill({ json: { items: [], next: null } });
    return route.fulfill({ json: [] });
  });
  return { revoke: () => { revoked = true; }, refreshes: () => refreshes };
}

async function login(page: Page) {
  await page.goto("/");
  await page.getByLabel("아이디", { exact: true }).fill("admin");
  await page.getByLabel("비밀번호", { exact: true }).fill("test-password!");
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page.getByRole("heading", { name: "어떤 업무를 기획하시겠어요?" })).toBeVisible();
}

test("Supabase 모드도 ID로 로그인하고 관리자 메뉴·새로고침·갱신·로그아웃을 지원한다", async ({ page }) => {
  const boundary = await authBoundary(page);
  await login(page);
  await expect(page.locator(".business-header-actions").getByRole("button", { name: "업무 연결 설정", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "관리자 메뉴 열기" }).click();
  await page.getByRole("navigation", { name: "관리자 메뉴", exact: true }).getByRole("button", { name: "계정 관리", exact: true }).click();
  await expect(page.getByRole("heading", { name: "계정 관리", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "admin 관리" })).toBeVisible();
  await page.evaluate(() => {
    const session = JSON.parse(sessionStorage.getItem("hplan-supabase-session.v1")!);
    session.expires_at = 0;
    sessionStorage.setItem("hplan-supabase-session.v1", JSON.stringify(session));
  });
  await page.reload();
  await expect(page.getByRole("heading", { name: "계정 관리", exact: true })).toBeVisible();
  expect(boundary.refreshes()).toBe(1);
  await page.getByLabel("계정 메뉴", { exact: true }).click();
  await page.getByRole("button", { name: "로그아웃", exact: true }).click();
  await expect(page.getByRole("form", { name: "로그인", exact: true })).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem("hplan-supabase-session.v1"))).toBeNull();
});

test("Supabase 일반 사용자는 모바일 관리자 주소가 차단되고 세션 해제를 반영한다", async ({ page }) => {
  const boundary = await authBoundary(page, "USER1");
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await page.goto("/?view=accounts");
  await expect(page.getByRole("heading", { name: "어떤 업무를 기획하시겠어요?" })).toBeVisible();
  await expect(page.getByRole("button", { name: "관리자 메뉴 열기" })).toHaveCount(0);
  boundary.revoke();
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("form", { name: "로그인", exact: true })).toBeVisible();
});
