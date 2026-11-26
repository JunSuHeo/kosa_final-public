import { expect, test, headers, loginHeaders } from "./server-fixture";
import { businessSource, login } from "./business-helpers";
import type { APIRequestContext, Page } from "@playwright/test";
import { execFileSync } from "node:child_process";

async function openAssignments(page: Page, request: APIRequestContext) {
  const source = await businessSource(request);
  const accounts: { id: string; loginId: string }[] = await (
    await request.get("/api/accounts/assignment-options", { headers })
  ).json();
  await login(page, `/?view=settings&source=${source.id}`);
  const panel = page.getByRole("region", { name: "유저 배정", exact: true });
  await expect(panel.getByLabel("user1 업무 배정", { exact: true })).toBeEnabled();
  return { source, accounts, panel };
}

test("선택·취소는 저장하지 않고 변경 항목만 저장하며 재접속과 배정 해제를 지원한다", async ({ page, request, context }) => {
  const { source, accounts, panel } = await openAssignments(page, request);
  const writes: string[] = [];
  page.on("request", (req) => {
    if (req.url().includes(`/api/sources/${source.id}/assignments/`) && ["PUT", "DELETE"].includes(req.method()))
      writes.push(`${req.method()} ${req.url()}`);
  });
  await expect(panel.getByLabel("admin 업무 배정", { exact: true })).toHaveCount(0);
  const first = panel.getByLabel("user1 업무 배정", { exact: true });
  const second = panel.getByLabel("user2 업무 배정", { exact: true });
  const save = panel.getByRole("button", { name: "배정 저장", exact: true });
  await expect(save).toBeDisabled();
  await first.check();
  await second.check();
  await expect(panel).toContainText("변경 2건");
  await expect.poll(() => writes.length).toBe(0);
  await panel.getByRole("button", { name: "변경 취소", exact: true }).click();
  await expect(first).not.toBeChecked();
  await expect(second).not.toBeChecked();
  await expect(save).toBeDisabled();
  await first.check();
  await second.check();
  await save.click();
  await expect(panel.getByRole("status")).toHaveText("업무 배정을 저장했습니다.");
  expect(writes).toHaveLength(2);
  await expect(save).toBeDisabled();
  await page.reload();
  await expect(first).toBeChecked();
  await expect(second).toBeChecked();
  const user = await context.newPage();
  await login(user, "/", "user1");
  await expect(user.locator(`.business-card[data-source-id="${source.id}"]`)).toBeEnabled();
  await expect(user.getByRole("region", { name: "유저 배정", exact: true })).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(save).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await page.screenshot({ path: "test-results/hplan-source-assignments-mobile.png", fullPage: true });
  await second.uncheck();
  await save.click();
  await expect(panel.getByRole("status")).toHaveText("업무 배정을 저장했습니다.");
  expect(writes).toHaveLength(3);
  expect(writes[2]).toContain(`DELETE ${process.env.E2E_BASE_URL}/api/sources/${source.id}/assignments/${accounts.find((a) => a.loginId === "user2")!.id}`);
});

test("부분 실패는 성공 항목을 확정하고 실패 선택만 다시 저장한다", async ({ page, request }) => {
  const { source, accounts, panel } = await openAssignments(page, request);
  const secondId = accounts.find((a) => a.loginId === "user2")!.id;
  let fail = true;
  const writes: string[] = [];
  await page.route(`**/api/sources/${source.id}/assignments/*`, async (route) => {
    writes.push(route.request().url());
    if (route.request().url().endsWith(`/${secondId}`) && fail) {
      await route.fulfill({ status: 503, json: { detail: "배정 저장 일시 실패" } });
    } else await route.continue();
  });
  await panel.getByLabel("user1 업무 배정", { exact: true }).check();
  await panel.getByLabel("user2 업무 배정", { exact: true }).check();
  await panel.getByRole("button", { name: "배정 저장", exact: true }).click();
  await expect(panel).toContainText("저장 실패: 배정 저장 일시 실패");
  await expect(panel).toContainText("배정 완료");
  await expect(panel).toContainText("변경 1건");
  await expect(panel.getByLabel("user2 업무 배정", { exact: true })).toBeChecked();
  fail = false;
  await panel.getByRole("button", { name: "배정 저장", exact: true }).click();
  await expect(panel.getByRole("status")).toHaveText("업무 배정을 저장했습니다.");
  expect(writes).toHaveLength(3);
  expect(writes[2]).toContain(`/${secondId}`);
});

test("저장은 순차 처리하고 응답이 유실되어도 서버 반영을 확인한다", async ({ page, request }) => {
  const { source, panel } = await openAssignments(page, request);
  let release!: () => void;
  const paused = new Promise<void>((resolve) => { release = resolve; });
  let started!: () => void;
  const reached = new Promise<void>((resolve) => { started = resolve; });
  let writes = 0;
  await page.route(`**/api/sources/${source.id}/assignments/*`, async (route) => {
    writes++;
    if (writes === 1) {
      await route.fetch();
      started();
      await paused;
      await route.abort("failed");
    } else await route.continue();
  });
  await panel.getByLabel("user1 업무 배정", { exact: true }).check();
  await panel.getByLabel("user2 업무 배정", { exact: true }).check();
  await panel.getByRole("button", { name: "배정 저장", exact: true }).click();
  await reached;
  try {
    await expect(panel.getByRole("button", { name: "배정 저장 중…", exact: true })).toBeDisabled();
    await expect(panel.getByLabel("user1 업무 배정", { exact: true })).toBeDisabled();
    await expect.soft(page.getByLabel("어떤 프로젝트를 기획할까요?", { exact: true })).toBeDisabled();
    await expect.soft(page.getByRole("button", { name: "업무 선택으로 돌아가기", exact: true })).toBeDisabled();
    expect(writes).toBe(1);
  } finally { release(); }
  await expect(panel.getByRole("status")).toHaveText("업무 배정을 저장했습니다.");
  expect(writes).toBe(2);
  await expect(panel).toContainText("변경 0건");
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("저장 뒤 조회 실패 시 재확인 전 저장을 막고 실패 선택을 보존한다", async ({ page, request }) => {
  const { source, accounts, panel } = await openAssignments(page, request);
  const secondId = accounts.find((a) => a.loginId === "user2")!.id;
  let failRead = true;
  let failWrite = true;
  await page.route(`**/api/sources/${source.id}/assignments`, async (route) => {
    if (failRead) await route.fulfill({ status: 503, json: { detail: "조회 일시 실패" } });
    else await route.continue();
  });
  await page.route(`**/api/sources/${source.id}/assignments/${secondId}`, async (route) => {
    if (failWrite) await route.fulfill({ status: 503, json: { detail: "배정 저장 일시 실패" } });
    else await route.continue();
  });
  await panel.getByLabel("user1 업무 배정", { exact: true }).check();
  await panel.getByLabel("user2 업무 배정", { exact: true }).check();
  await panel.getByRole("button", { name: "배정 저장", exact: true }).click();
  await expect(panel).toContainText("저장 결과 확인 필요");
  await expect(panel.getByRole("button", { name: "배정 저장", exact: true })).toBeDisabled();
  failRead = false;
  await panel.getByRole("button", { name: "배정 다시 조회", exact: true }).click();
  await expect(panel).toContainText("변경 1건");
  await expect(panel.getByLabel("user1 업무 배정", { exact: true })).toBeChecked();
  await expect(panel.getByLabel("user2 업무 배정", { exact: true })).toBeChecked();
  failWrite = false;
  await panel.getByRole("button", { name: "배정 저장", exact: true }).click();
  await expect(panel.getByRole("status")).toHaveText("업무 배정을 저장했습니다.");
});

test("업무 전환은 미저장 선택을 초기화하고 이전 업무의 늦은 조회를 무시한다", async ({ page, request }) => {
  const source = await businessSource(request);
  const branch = execFileSync("git", ["-C", `${process.env.STUDIO_REPOSITORY_HOST_ROOT}/${process.env.E2E_FIXTURE_REPO}`, "symbolic-ref", "--short", "HEAD"], { encoding: "utf8" }).trim();
  const other = await (await request.post("/api/sources", { headers, data: {
    name: "다른 업무", description: "전환 검증", kind: "local", repository: process.env.E2E_FIXTURE_REPO, ref: branch,
  } })).json();
  const snapshot = await (await request.post(`/api/sources/${other.id}/analyze`, { headers, data: {} })).json();
  await expect.poll(async () => (await (await request.get(`/api/sources/${other.id}/snapshots/${snapshot.id}`, { headers })).json()).status).toBe("ready");
  const preview = await (await request.post(`/api/sources/${other.id}/snapshots/${snapshot.id}/publication-preview`, { headers, data: {} })).json();
  expect((await request.post(`/api/sources/${other.id}/publish`, { headers, data: { snapshot_id: snapshot.id, fingerprint: preview.fingerprint, design_profile: preview.design_profile } })).ok()).toBeTruthy();
  const user1 = (await (await request.get("/api/accounts/assignment-options", { headers })).json()).find((a: { loginId: string }) => a.loginId === "user1");
  await request.put(`/api/sources/${other.id}/assignments/${user1.id}`, { headers });
  await login(page, `/?view=settings&source=${source.id}`);
  const panel = page.getByRole("region", { name: "유저 배정", exact: true });
  await panel.getByLabel("user2 업무 배정", { exact: true }).check();
  await page.getByLabel("어떤 프로젝트를 기획할까요?", { exact: true }).selectOption(other.id);
  await expect(panel.getByLabel("user1 업무 배정", { exact: true })).toBeChecked();
  await expect(panel.getByLabel("user2 업무 배정", { exact: true })).not.toBeChecked();
  let release!: () => void;
  const paused = new Promise<void>((resolve) => { release = resolve; });
  let started!: () => void;
  const reached = new Promise<void>((resolve) => { started = resolve; });
  await page.route(`**/api/sources/${source.id}/assignments`, async (route) => {
    const response = await route.fetch();
    started();
    await paused;
    await route.fulfill({ response });
  });
  await page.getByLabel("어떤 프로젝트를 기획할까요?", { exact: true }).selectOption(source.id);
  await reached;
  await page.getByLabel("어떤 프로젝트를 기획할까요?", { exact: true }).selectOption(other.id);
  await expect(panel.getByLabel("user1 업무 배정", { exact: true })).toBeChecked();
  const previousResponse = page.waitForResponse((response) => response.url().endsWith(`/api/sources/${source.id}/assignments`));
  release();
  await (await previousResponse).finished();
  await expect(panel.getByLabel("user1 업무 배정", { exact: true })).toBeChecked();
  await expect(panel).toContainText("변경 0건");
  await expect(panel).toContainText("업무를 전환하면 저장 전 선택은 초기화됩니다.");
});

test("배정 권한이 없는 소유자와 배정받은 유저에게는 배정 영역을 표시하지 않는다", async ({ page, request }) => {
  const source = await businessSource(request);
  const user = (await (await request.get("/api/accounts/assignment-options", { headers })).json()).find((a: { loginId: string }) => a.loginId === "user1");
  await request.put(`/api/sources/${source.id}/assignments/${user.id}`, { headers });
  await request.put("/api/roles/USER1/sources.manage", { headers, data: { enabled: true } });
  const userHeaders = await loginHeaders(request, "user1");
  const owned = await (await request.post("/api/sources", { headers: userHeaders, data: {
    name: "유저 소유 업무", description: "배정 권한 없음", kind: "local", repository: process.env.E2E_FIXTURE_REPO, ref: "HEAD",
  } })).json();
  await login(page, `/?view=settings&source=${owned.id}`, "user1");
  await expect(page.getByRole("heading", { name: "업무 연결 설정", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "유저 배정", exact: true })).toHaveCount(0);
  await page.goto(`/?view=settings&source=${source.id}`);
  await expect(page.getByRole("heading", { name: "업무 연결 설정", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "유저 배정", exact: true })).toHaveCount(0);
});

test("최초 조회 실패는 다시 조회할 수 있고 사용 중지 계정은 후보에서 제외한다", async ({ page, request }) => {
  const source = await businessSource(request);
  const user = (await (await request.get("/api/accounts", { headers })).json()).find((account: { loginId: string }) => account.loginId === "user2");
  expect((await request.patch(`/api/accounts/${user.id}`, { headers, data: { name: user.name, role: user.role, active: false } })).ok()).toBeTruthy();
  let fail = true;
  await page.route(`**/api/sources/${source.id}/assignments`, async (route) => {
    if (fail) await route.fulfill({ status: 503, json: { detail: "초기 조회 일시 실패" } });
    else await route.continue();
  });
  await login(page, `/?view=settings&source=${source.id}`);
  const panel = page.getByRole("region", { name: "유저 배정", exact: true });
  await expect(panel).toContainText("초기 조회 일시 실패");
  await expect(panel.getByRole("button", { name: "배정 저장", exact: true })).toBeDisabled();
  fail = false;
  await panel.getByRole("button", { name: "배정 다시 조회", exact: true }).click();
  await expect(panel.getByLabel("user1 업무 배정", { exact: true })).toBeEnabled();
  await expect(panel.getByLabel("user2 업무 배정", { exact: true })).toHaveCount(0);
});

test("선택 뒤 비활성화된 실패 계정은 이름과 결과를 유지하고 개별 취소할 수 있다", async ({ page, request }) => {
  const { panel } = await openAssignments(page, request);
  const user = (await (await request.get("/api/accounts", { headers })).json()).find((account: { loginId: string }) => account.loginId === "user2");
  await panel.getByLabel("user1 업무 배정", { exact: true }).check();
  await panel.getByLabel("user2 업무 배정", { exact: true }).check();
  expect((await request.patch(`/api/accounts/${user.id}`, { headers, data: { name: user.name, role: user.role, active: false } })).ok()).toBeTruthy();
  await panel.getByRole("button", { name: "배정 저장", exact: true }).click();
  const failed = panel.getByRole("group", { name: "user2 배정 실패", exact: true });
  await expect(failed).toContainText("user2");
  await expect(failed).toContainText("사용 가능한 계정을 찾을 수 없습니다.");
  await expect(panel.getByLabel("user2 업무 배정", { exact: true })).toHaveCount(0);
  await expect(panel).toContainText("변경 1건");
  await failed.getByRole("button", { name: "선택 취소", exact: true }).click();
  await expect(panel).toContainText("변경 0건");
  await expect(panel.getByLabel("user1 업무 배정", { exact: true })).toBeChecked();
  await expect(panel.getByRole("button", { name: "배정 저장", exact: true })).toBeDisabled();
});
