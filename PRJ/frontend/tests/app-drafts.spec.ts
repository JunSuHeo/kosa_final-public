import { expect, test, type Page } from "@playwright/test";

const snapshot = { prd: { title: "발주 업무", roles: ["담당자"], platforms: ["desktop"], assumptions: [], sections: [{ id: "prd-goal", group: "개요", title: "제품 목표와 핵심 범위", content: "기존 확인본의 목표" }] }, requirements: [], features: [], flow: { nodes: [], edges: [] }, screens: [] };
const id = "11111111-1111-4111-8111-111111111111";
async function boundary(page: Page) {
  const permissions = ["plans.read", "plans.create", "plans.edit", "plans.confirm", "plans.export"];
  const policy = Object.fromEntries(["USER1", "USER2", "ADMINISTRATOR"].map(role => [role, Object.fromEntries(permissions.map(p => [p, true]))]));
  const identity = { account: { id: "draft-owner", loginId: "worker", name: "업무 담당자", role: "USER1", active: true }, policy };
  let version = 1;
  const project = () => ({ id, source_id: null, title: "발주 업무", idea: "발주 승인 개선", current_version: version, updated_at: new Date().toISOString() });
  await page.route("**/health", route => route.fulfill({ json: { auth_mode: "supabase", ai_mode: "mock", status: "ok" } }));
  await page.route("**/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/login") return route.fulfill({ json: { access_token: "fixture", refresh_token: "fixture-refresh", expires_in: 3600, identity } });
    if (path === "/api/auth/me") return route.fulfill({ json: identity });
    if (path === "/api/auth/logout") return route.fulfill({ json: { ok: true } });
    if (path === "/api/projects") return route.fulfill({ json: [project()] });
    if (path === `/api/projects/${id}`) return route.fulfill({ json: { project: project(), revision: { version, snapshot }, proposal: null, job: null, messages: [], revisions: [], screen_previews: [] } });
    if (path.includes("/reviews")) return route.fulfill({ json: null });
    return route.fulfill({ json: [] });
  });
  await page.goto(`/?project=${id}`);
  await page.getByLabel("아이디", { exact: true }).fill("worker");
  await page.getByLabel("비밀번호", { exact: true }).fill("fixture-password");
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page.getByRole("button", { name: "직접 편집", exact: true })).toBeVisible();
  return { advance: () => { version++; } };
}

test("직접 편집은 같은 탭 새로고침 후 복원하고 확인본은 바꾸지 않는다", async ({ page }) => {
  await boundary(page);
  await page.getByRole("button", { name: "직접 편집", exact: true }).click();
  await page.getByLabel("제품 목표와 핵심 범위 편집").fill("현업에서 작성 중인 목표");
  await expect(page.locator(".header-status")).toContainText("직접 편집 미저장");
  await page.reload();
  await expect(page.getByLabel("제품 목표와 핵심 범위 편집")).toHaveValue("현업에서 작성 중인 목표");
  await expect(page.locator(".snapshot-switch")).toContainText("현업 확인본 v1");
  await page.getByRole("button", { name: "취소", exact: true }).click();
  await page.reload();
  await expect(page.getByRole("button", { name: "직접 편집", exact: true })).toBeVisible();
});

test("다른 기준 버전이 생긴 직접 편집은 자동 적용하지 않고 보관 사실을 알린다", async ({ page }) => {
  const state = await boundary(page);
  await page.getByRole("button", { name: "직접 편집", exact: true }).click();
  await page.getByLabel("제품 목표와 핵심 범위 편집").fill("이전 기준에서 작성한 내용");
  state.advance();
  await page.reload();
  await expect(page.getByRole("alert").filter({ hasText: "다른 기준" })).toBeVisible();
  await expect(page.getByLabel("제품 목표와 핵심 범위 편집")).toHaveCount(0);
  await page.getByRole("button", { name: "임시 편집 버리기", exact: true }).click();
  await page.reload();
  await expect(page.getByRole("alert").filter({ hasText: "다른 기준" })).toHaveCount(0);
});
