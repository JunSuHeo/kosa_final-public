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
  let transient: number | "network" | null = null;
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
    if (["/api/auth/me", "/api/auth/refresh"].includes(path) && transient) {
      if (transient === "network") return route.abort("failed");
      return route.fulfill({ status: transient, json: { detail: "인증 서버에 잠시 연결할 수 없습니다." } });
    }
    if (path === "/api/auth/refresh") { refreshes++; return route.fulfill({ status: revoked ? 401 : 200, json: revoked ? { detail: "로그인 만료" } : token() }); }
    if (path === "/api/auth/logout") { revoked = true; return route.fulfill({ json: { ok: true } }); }
    if (path === "/api/auth/me") return route.fulfill({ status: revoked ? 401 : 200, json: revoked ? { detail: "다시 로그인해 주세요" } : identity });
    if (path === "/api/accounts") return route.fulfill({ json: [identity.account] });
    if (path === "/api/roles") return route.fulfill({ json: policy });
    if (path === "/api/audit") return route.fulfill({ json: { items: [], next: null } });
    return route.fulfill({ json: [] });
  });
  return { revoke: () => { revoked = true; }, refreshes: () => refreshes, fail: (status: number | "network" | null) => { transient = status; } };
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

for (const failure of ["network", 429, 503] as const) {
  test(`인증 확인 ${failure} 오류에도 현재 화면과 입력을 유지한다`, async ({ page }) => {
    const boundary = await authBoundary(page);
    await login(page);
    await page.getByRole("button", { name: "관리자 메뉴 열기" }).click();
    await page.getByRole("navigation", { name: "관리자 메뉴", exact: true }).getByRole("button", { name: "계정 관리", exact: true }).click();
    await page.getByRole("button", { name: "admin 관리" }).click();
    await page.getByLabel("표시 이름", { exact: true }).fill("저장 전 이름");
    boundary.fail(failure);
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await expect(page.getByRole("heading", { name: "계정 관리", exact: true })).toBeVisible();
    await expect(page.getByLabel("표시 이름", { exact: true })).toHaveValue("저장 전 이름");
    await expect(page.getByRole("form", { name: "로그인", exact: true })).toHaveCount(0);
    boundary.fail(null);
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await expect(page.getByLabel("표시 이름", { exact: true })).toHaveValue("저장 전 이름");
  });
}

test("저장된 세션 확인이 일시 실패하면 재로그인 대신 재시도하고 가짜 identity는 쓰지 않는다", async ({ page }) => {
  const boundary = await authBoundary(page);
  await login(page);
  await page.evaluate(() => {
    const session = JSON.parse(sessionStorage.getItem("hplan-supabase-session.v1")!);
    session.expires_at = 0;
    sessionStorage.setItem("hplan-supabase-session.v1", JSON.stringify(session));
    sessionStorage.setItem("hplan-session.v2", JSON.stringify({ account: { role: "ADMINISTRATOR" } }));
  });
  boundary.fail(503);
  await page.reload();
  await expect(page.getByRole("button", { name: "다시 연결", exact: true })).toBeVisible();
  await expect(page.getByRole("form", { name: "로그인", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "관리자 메뉴 열기" })).toHaveCount(0);
  boundary.fail(null);
  await page.getByRole("button", { name: "다시 연결", exact: true }).click();
  await expect(page.getByRole("heading", { name: "어떤 업무를 기획하시겠어요?" })).toBeVisible();
});

test("감사 이력 200개 뒤의 항목을 중복 없이 추가하며 실패 후 같은 커서로 재시도한다", async ({ page }) => {
  await authBoundary(page);
  const entry = (i: number) => ({ id: `audit-${i}`, at: "2026-11-23T00:00:00Z", actor: "admin", action: "계정 변경", target: `대상 ${i}`, detail: `기록 ${i}` });
  let failOlder = true;
  await page.route("**/api/audit?**", async route => {
    const cursor = new URL(route.request().url()).searchParams.get("before");
    if (!cursor) return route.fulfill({ json: { items: Array.from({ length: 200 }, (_, i) => entry(i)), next: "9007199254740993" } });
    if (cursor !== "9007199254740993") return route.fulfill({ status: 400, json: { detail: "잘못된 커서" } });
    if (failOlder) return route.fulfill({ status: 503, json: { detail: "이력을 불러오지 못했습니다." } });
    return route.fulfill({ json: { items: [entry(199), entry(200)], next: null } });
  });
  await login(page);
  await page.getByRole("button", { name: "관리자 메뉴 열기" }).click();
  await page.getByRole("navigation", { name: "관리자 메뉴", exact: true }).getByRole("button", { name: "변경 이력", exact: true }).click();
  await expect(page.locator("tbody tr")).toHaveCount(200);
  await page.getByRole("button", { name: "이전 이력 더 보기", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("이력을 불러오지 못했습니다.");
  await expect(page.locator("tbody tr")).toHaveCount(200);
  failOlder = false;
  await page.getByRole("button", { name: "다시 시도", exact: true }).click();
  await expect(page.locator("tbody tr")).toHaveCount(201);
  await expect(page.getByRole("cell", { name: "기록 200", exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "기록 199", exact: true })).toHaveCount(1);
  await expect(page.getByRole("button", { name: "이전 이력 더 보기", exact: true })).toHaveCount(0);
});

test("비밀번호 재설정의 응답 불명확 안내와 작업 ID를 재인증 후 유지한다", async ({ page }) => {
  await authBoundary(page);
  const ids: string[] = [];
  await page.route("**/api/accounts/demo-user/reset-password", async route => {
    ids.push(route.request().postDataJSON().operation_id);
    if (ids.length === 1) return route.fulfill({ status: 503, json: { detail: { code: "auth_write_uncertain", message: "다시 로그인이 필요하면 기존 또는 새 비밀번호로 확인한 뒤 같은 작업을 다시 시도해 주세요." } } });
    if (ids.length === 2) return route.fulfill({ status: 401, json: { detail: "다시 로그인해 주세요" } });
    return route.fulfill({ json: { ok: true } });
  });
  await login(page);
  await page.getByRole("button", { name: "관리자 메뉴 열기" }).click();
  await page.getByRole("navigation", { name: "관리자 메뉴", exact: true }).getByRole("button", { name: "계정 관리", exact: true }).click();
  await page.getByRole("button", { name: "admin 관리" }).click();
  await page.getByLabel("새 비밀번호", { exact: true }).fill("replacement-password!");
  await page.getByRole("button", { name: "비밀번호 재설정", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("다시 로그인이 필요하면 기존 또는 새 비밀번호로 확인한 뒤 같은 작업을 다시 시도해 주세요.");
  await page.getByRole("button", { name: "비밀번호 재설정", exact: true }).click();
  await expect(page.getByRole("form", { name: "로그인", exact: true })).toBeVisible();
  await page.getByLabel("아이디", { exact: true }).fill("admin");
  await page.getByLabel("비밀번호", { exact: true }).fill("test-password!");
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await page.getByRole("button", { name: "admin 관리" }).click();
  await page.getByLabel("새 비밀번호", { exact: true }).fill("replacement-password!");
  await page.getByRole("button", { name: "비밀번호 재설정", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("비밀번호를 재설정하고 기존 세션을 종료했습니다.");
  expect(ids).toHaveLength(3);
  expect(ids[0]).toMatch(/^[0-9a-f-]{36}$/);
  expect(ids).toEqual([ids[0], ids[0], ids[0]]);
  expect(await page.evaluate(() => sessionStorage.getItem("hplan-account-operations.v1"))).toBe("{}");
});

test("감사 이력이 201건 늘어 기존 페이지와 겹치지 않으면 새 경계부터 빠짐없이 다시 조회한다", async ({ page }) => {
  await authBoundary(page);
  let latest = 200;
  const entry = (i: number) => ({ id: String(i), at: "2026-11-23T00:00:00Z", actor: "admin", action: "계정 변경", target: `대상 ${i}`, detail: `기록 ${i}` });
  await page.route("**/api/audit?**", route => {
    const before = new URL(route.request().url()).searchParams.get("before");
    const head = before ? Number(before) - 1 : latest;
    const low = Math.max(1, head - 199);
    return route.fulfill({ json: { items: Array.from({ length: head - low + 1 }, (_, i) => entry(head - i)), next: low > 1 ? String(low) : null } });
  });
  await login(page);
  await page.getByRole("button", { name: "관리자 메뉴 열기" }).click();
  await page.getByRole("navigation", { name: "관리자 메뉴", exact: true }).getByRole("button", { name: "변경 이력", exact: true }).click();
  await expect(page.locator("tbody tr")).toHaveCount(200);
  latest = 401;
  const refreshed = page.waitForResponse(response => new URL(response.url()).pathname === "/api/audit");
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await refreshed;
  await expect(page.getByRole("cell", { name: "기록 401", exact: true })).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(200);
  await page.getByRole("button", { name: "이전 이력 더 보기", exact: true }).click();
  await expect(page.locator("tbody tr")).toHaveCount(400);
  latest = 402;
  const overlappingRefresh = page.waitForResponse(response => new URL(response.url()).pathname === "/api/audit");
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await overlappingRefresh;
  await expect(page.locator("tbody tr")).toHaveCount(401);
  await page.getByRole("button", { name: "이전 이력 더 보기", exact: true }).click();
  await expect(page.locator("tbody tr")).toHaveCount(402);
  await expect(page.getByRole("cell", { name: "기록 201", exact: true })).toHaveCount(1);
  await expect(page.getByRole("cell", { name: "기록 1", exact: true })).toHaveCount(1);
});

for (const kind of ["reset", "create"] as const) {
  for (const reload of [false, true]) {
    test(`${kind} 응답 유실 뒤 ${reload ? "새로고침한 같은" : "변경한"} 비밀번호는 완료 작업 ID를 재사용하지 않는다`, async ({ page }) => {
      await authBoundary(page);
      await login(page);
      const ids: string[] = [];
      const completed = new Set<string>();
      let actualPassword = "";
      await page.route(kind === "reset" ? "**/api/accounts/demo-user/reset-password" : "**/api/accounts", async route => {
        if (route.request().method() !== "POST") return route.fallback();
        const input = route.request().postDataJSON();
        ids.push(input.operation_id);
        if (kind === "create" && ids.length > 1 && !completed.has(input.operation_id))
          return route.fulfill({ status: 409, json: { detail: "이미 사용 중인 ID입니다." } });
        if (!completed.has(input.operation_id)) {
          completed.add(input.operation_id);
          actualPassword = input.password;
        }
        if (ids.length === 1) return route.fulfill({ status: 503, json: { detail: "응답을 확인하지 못했습니다." } });
        return route.fulfill({ json: { id: "created-account", loginId: "worker", name: "실무자", role: "USER1", active: true, sessionVersion: 1, createdAt: "2026-11-23T00:00:00Z", lastLoginAt: null } });
      });
      await page.getByRole("button", { name: "관리자 메뉴 열기" }).click();
      await page.getByRole("navigation", { name: "관리자 메뉴", exact: true }).getByRole("button", { name: "계정 관리", exact: true }).click();
      const submit = async (password: string) => {
        if (kind === "reset") {
          await page.getByRole("button", { name: "admin 관리" }).click();
          await page.getByLabel("새 비밀번호", { exact: true }).fill(password);
          await page.getByRole("button", { name: "비밀번호 재설정", exact: true }).click();
        } else {
          await page.getByRole("button", { name: "계정 등록", exact: true }).click();
          await page.getByLabel("로그인 ID", { exact: true }).fill("worker");
          await page.getByLabel("표시 이름", { exact: true }).fill("실무자");
          await page.getByLabel("초기 비밀번호", { exact: true }).fill(password);
          await page.getByRole("button", { name: "등록하기", exact: true }).click();
        }
      };
      await submit("first-password!");
      await expect(page.getByRole("alert")).toContainText("응답을 확인하지 못했습니다.");
      if (reload) {
        await page.reload();
        await expect(page.getByRole("heading", { name: "계정 관리", exact: true })).toBeVisible();
      }
      const password = reload ? "first-password!" : "second-password!";
      await submit(password);
      if (kind === "create") await expect(page.getByRole("alert")).toContainText("이미 사용 중인 ID입니다.");
      else await expect(page.getByRole("status")).toContainText("비밀번호를 재설정하고 기존 세션을 종료했습니다.");
      expect(ids).toHaveLength(2);
      expect(ids[1]).not.toBe(ids[0]);
      expect(actualPassword).toBe(kind === "create" ? "first-password!" : password);
      const storage = await page.evaluate(() => JSON.stringify({ local: { ...localStorage }, session: { ...sessionStorage } }));
      expect(storage).not.toContain("first-password!");
      expect(storage).not.toContain("second-password!");
    });
  }
}

test("다른 작업에 밀린 재설정 409는 자동 재전송하지 않고 다음 제출에 새 작업 ID를 쓴다", async ({ page }) => {
  await authBoundary(page);
  await login(page);
  const ids: string[] = [];
  await page.route("**/api/accounts/demo-user/reset-password", route => {
    ids.push(route.request().postDataJSON().operation_id);
    if (ids.length === 1) return route.fulfill({ status: 409, json: { detail: { code: "account_operation_superseded", message: "다른 비밀번호 재설정이 완료되었습니다. 다시 제출하면 새 작업으로 진행합니다." } } });
    return route.fulfill({ json: { ok: true } });
  });
  await page.getByRole("button", { name: "관리자 메뉴 열기" }).click();
  await page.getByRole("navigation", { name: "관리자 메뉴", exact: true }).getByRole("button", { name: "계정 관리", exact: true }).click();
  await page.getByRole("button", { name: "admin 관리" }).click();
  await page.getByLabel("새 비밀번호", { exact: true }).fill("replacement-password!");
  await page.getByRole("button", { name: "비밀번호 재설정", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("다시 제출하면 새 작업으로 진행합니다.");
  expect(ids).toHaveLength(1);
  await page.getByRole("button", { name: "비밀번호 재설정", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("비밀번호를 재설정하고 기존 세션을 종료했습니다.");
  expect(ids).toHaveLength(2);
  expect(ids[1]).not.toBe(ids[0]);
});

test("미완료 계정 생성은 새로고침 뒤 새 비밀번호와 새 작업 ID로 같은 계정을 복구한다", async ({ page }) => {
  await authBoundary(page);
  let pending: { loginId: string; name: string; role: string } | null = null;
  const ids: string[] = [];
  let actualPassword = "";
  const account = { id: "pending-worker", loginId: "worker", name: "실무자", role: "USER1", active: true, sessionVersion: 1, createdAt: "2026-11-23T00:00:00Z", lastLoginAt: null };
  await page.route("**/api/accounts", async route => {
    if (route.request().method() !== "POST") return route.fallback();
    const input = route.request().postDataJSON();
    ids.push(input.operation_id);
    if (!pending) {
      pending = { loginId: input.loginId, name: input.name.trim(), role: input.role };
      return route.fulfill({ status: 503, json: { detail: "인증 서버에 잠시 연결할 수 없습니다." } });
    }
    if (input.loginId !== pending.loginId || input.name.trim() !== pending.name || input.role !== pending.role)
      return route.fulfill({ status: 409, json: { detail: "이미 사용 중인 ID입니다." } });
    actualPassword = input.password;
    return route.fulfill({ status: 201, json: account });
  });
  await login(page);
  await page.getByRole("button", { name: "관리자 메뉴 열기" }).click();
  await page.getByRole("navigation", { name: "관리자 메뉴", exact: true }).getByRole("button", { name: "계정 관리", exact: true }).click();
  const register = async (password: string) => {
    await page.getByRole("button", { name: "계정 등록", exact: true }).click();
    await page.getByLabel("로그인 ID", { exact: true }).fill("worker");
    await page.getByLabel("표시 이름", { exact: true }).fill("실무자");
    await page.getByLabel("초기 비밀번호", { exact: true }).fill(password);
    await page.getByRole("button", { name: "등록하기", exact: true }).click();
  };
  await register("first-password!");
  await expect(page.getByRole("alert")).toContainText("인증 서버에 잠시 연결할 수 없습니다.");
  await page.reload();
  await expect(page.getByRole("heading", { name: "계정 관리", exact: true })).toBeVisible();
  await register("replacement-password!");
  await expect(page.getByRole("status")).toContainText("계정을 등록했습니다.");
  await expect(page.getByRole("heading", { name: "worker 계정", exact: true })).toBeVisible();
  expect(ids).toHaveLength(2);
  expect(ids[1]).not.toBe(ids[0]);
  expect(actualPassword).toBe("replacement-password!");
  expect(await page.evaluate(() => sessionStorage.getItem("hplan-account-operations.v1"))).toBe("{}");
});
