import { test, expect, type Page } from "@playwright/test";
import type { Bundle, Job, Snapshot } from "../src/types";

const conversationId = "11111111-1111-4111-8111-111111111111";
const documentsId = "22222222-2222-4222-8222-222222222222";
const snapshot: Snapshot = {
  prd: {
    title: "발주 업무", roles: [], platforms: [], assumptions: [],
    sections: [{ id: "goal", group: "개요", title: "제품 목표", content: "발주 승인 개선" }],
  },
  requirements: [], features: [],
  flow: { nodes: [], edges: [] },
  screens: ["desktop", "mobile"].map((device) => ({
    id: device, node_id: `node-${device}`, title: `${device} 시안`,
    device: device as "desktop" | "mobile",
    blocks: [{ id: `heading-${device}`, type: "heading", label: "발주 승인", content: "업무 확인", target_screen_id: null }],
  })),
};
function bundle(id: string, empty = false): Bundle {
  const value = structuredClone(snapshot);
  if (empty) { value.prd.sections = []; value.screens = []; }
  const now = new Date().toISOString();
  return {
    project: {
      id, source_id: null, code_snapshot_id: null, forked_from: null,
      title: "발주 업무", idea: "승인 개선", current_version: empty ? 0 : 1,
      created_at: now, updated_at: now,
      conversation_brief: { current_work: "발주", problem: "대기", desired_change: "승인 개선", actors: [], rules: [], exceptions: [], confirmed_facts: [], user_statements: [], open_questions: [] },
    },
    revision: { version: empty ? 0 : 1, summary: "기획", created_at: now, snapshot: value },
    proposal: null, job: null, messages: [], revisions: [],
  };
}
async function setup(page: Page, options: { documents?: boolean; legacy?: string } = {}) {
  const all = { [conversationId]: bundle(conversationId, true), [documentsId]: bundle(documentsId) };
  const permissions = ["plans.read", "plans.create", "plans.edit", "plans.confirm"];
  const identity = { account: { id: "layout-owner", loginId: "worker", name: "담당자", role: "USER1", active: true }, policy: { USER1: Object.fromEntries(permissions.map(p => [p, true])) } };
  await page.route("**/health", route => route.fulfill({ json: { auth_mode: "supabase", ai_mode: "mock", status: "ok" } }));
  await page.route("**/api/**", route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (path === "/api/auth/login") return route.fulfill({ json: { access_token: "layout-fixture", refresh_token: "refresh", expires_in: 3600, identity } });
    if (path === "/api/auth/me") return route.fulfill({ json: identity });
    if (path === "/api/projects") return route.fulfill({ json: Object.values(all).map(item => item.project) });
    const match = path.match(/^\/api\/projects\/([^/]+)(.*)$/);
    if (match && all[match[1]]) {
      const value = all[match[1]];
      if (match[2] === "/jobs" && request.method() === "POST") {
        value.job = { ...request.postDataJSON(), status: "running", stage: "prd", questions: [], answers: {}, partial: {}, usage: [], error: null };
        return route.fulfill({ json: value.job });
      }
      if (!match[2]) return route.fulfill({ json: value });
    }
    return route.fulfill({ json: [] });
  });
  if (options.legacy) await page.addInitScript(value => {
    if (!localStorage.getItem("hplan-workspace-ratio.v1")) localStorage.setItem("hplan-workspace-ratio.v1", value);
  }, options.legacy);
  await page.goto(`/?project=${options.documents ? documentsId : conversationId}`);
  await page.getByLabel("아이디", { exact: true }).fill("worker");
  await page.getByLabel("비밀번호", { exact: true }).fill("fixture-password");
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page.locator(".studio")).toBeVisible();
  return all;
}
async function expectWidth(page: Page, width: number) {
  await expect.poll(async () => (await page.locator(".side-panel").boundingBox())!.width).toBeCloseTo(width, 0);
}
async function dragTo(page: Page, x: number) {
  const box = (await page.getByRole("separator").boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, 300);
  await page.mouse.down();
  await page.mouse.move(x, 300, { steps: 8 });
  await page.mouse.up();
}

test("저장된 초안이 나타날 때 대화창을 줄이고 갱신 후에도 조절값을 유지한다", async ({ page }) => {
  const all = await setup(page);
  await expectWidth(page, 570); // (1440 - rail 76 - divider 8) * 42%
  await page.locator(".draft-action").click();
  await expect(page.locator(".studio")).toHaveAttribute("data-stage", "conversation");
  all[conversationId].job!.partial = { prd: snapshot.prd };
  await page.waitForResponse(async response => response.url().endsWith(`/api/projects/${conversationId}`) && !!(await response.json()).job?.partial?.prd);
  await expectWidth(page, 570);
  all[conversationId].proposal = { id: "first-draft", base_version: 0, candidate: snapshot, summary: "초안", issues: [], diff: [] };
  all[conversationId].job!.status = "waiting_review";
  await expect(page.locator(".studio")).toHaveAttribute("data-stage", "documents");
  await expectWidth(page, 407);
  await expect(page.locator(".document-page")).toContainText("발주 승인 개선");
  await dragTo(page, 620);
  const adjusted = (await page.locator(".side-panel").boundingBox())!.width;
  all[conversationId].job!.status = "running";
  await page.reload();
  await expectWidth(page, adjusted);
  all[conversationId].proposal!.id = "revised-draft";
  all[conversationId].job!.status = "waiting_review";
  await page.waitForResponse(async response => response.url().endsWith(`/api/projects/${conversationId}`) && (await response.json()).proposal?.id === "revised-draft");
  await expectWidth(page, adjusted);
  await page.goto(`/?project=${documentsId}`);
  await expectWidth(page, adjusted);
  await page.getByRole("separator").dblclick();
  await expectWidth(page, 407);
});

test("기존 저장 폭은 대화에서만 복원하고 단계별 드래그와 기본값을 따로 기억한다", async ({ page }) => {
  await setup(page, { legacy: "0.5" });
  await expectWidth(page, 678);
  await dragTo(page, 700);
  const conversationWidth = (await page.locator(".side-panel").boundingBox())!.width;
  await page.goto(`/?project=${documentsId}`);
  await expectWidth(page, 407);
  await dragTo(page, 600);
  const documentsWidth = (await page.locator(".side-panel").boundingBox())!.width;
  await page.goto(`/?project=${conversationId}`);
  await expectWidth(page, conversationWidth);
  await page.getByRole("separator").dblclick();
  await expectWidth(page, 570);
  await page.goto(`/?project=${documentsId}`);
  await expectWidth(page, documentsWidth);
});

for (const status of ["failed", "cancelled"]) {
  test(`초안 없는 생성 ${status} 상태는 대화 폭을 유지한다`, async ({ page }) => {
    const all = await setup(page);
    all[conversationId].job = { id: "generation", kind: "generate", status, stage: "prd", base_version: 0, request: "", error: status === "failed" ? "생성 실패" : null, questions: [], answers: {}, partial: { prd: snapshot.prd }, usage: [] } satisfies Job;
    await page.reload();
    await expect(page.locator(".studio")).toHaveAttribute("data-stage", "conversation");
    await expectWidth(page, 570);
  });
}

async function expectCentered(page: Page) {
  await expect.poll(() => page.locator(".wire-canvas").evaluate(canvas => {
    const sheet = canvas.querySelector(".wire-page")!.getBoundingClientRect();
    const viewport = canvas.getBoundingClientRect();
    return Math.abs((sheet.left + sheet.right) / 2 - (viewport.left + canvas.clientWidth / 2));
  })).toBeLessThanOrEqual(2);
}

test("상세 시안은 확대·축소와 속성 패널 전환 후에도 캔버스 중앙에 놓인다", async ({ page }) => {
  await page.setViewportSize({ width: 1800, height: 1000 });
  await setup(page, { documents: true });
  await page.getByRole("tab", { name: "화면 시안", exact: true }).click();
  await page.locator(".wire-thumbnail").first().click();
  await expect(page.locator(".zoom-value")).toHaveText("85%");
  await expectCentered(page);
  await page.screenshot({ path: "test-results/workspace-centered-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await expectCentered(page);
  await expect.poll(() => page.locator(".wire-canvas").evaluate(element => element.scrollWidth - element.clientWidth)).toBeLessThanOrEqual(1);
  await page.setViewportSize({ width: 1800, height: 1000 });
  await page.getByRole("button", { name: "화면 속성 패널" }).click();
  await expectCentered(page);
  await page.getByRole("button", { name: "와이어프레임 확대" }).click();
  await expectCentered(page);
  await page.getByRole("button", { name: "와이어프레임 축소" }).click();
  await page.getByRole("button", { name: "와이어프레임 축소" }).click();
  await expectCentered(page);
  await page.getByRole("button", { name: "미리보기", exact: true }).click();
  await expectCentered(page);
  await page.getByRole("button", { name: "다음 화면" }).click();
  await expect(page.locator(".wire-page")).toHaveClass(/mobile/);
  await expectCentered(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "산출물", exact: true }).click();
  await page.getByRole("button", { name: "와이어프레임 축소" }).click();
  await expectCentered(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await page.screenshot({ path: "test-results/workspace-centered-mobile.png", fullPage: true });
});

test("좁은 화면의 속성 패널도 시안을 덮지 않고 캔버스 너비에서 제외된다", async ({ page }) => {
  await page.setViewportSize({ width: 700, height: 1000 });
  await setup(page, { documents: true });
  await page.getByRole("button", { name: "산출물", exact: true }).click();
  await page.getByRole("tab", { name: "화면 시안", exact: true }).click();
  await page.locator(".wire-thumbnail").nth(1).click();
  await page.getByRole("button", { name: "화면 속성 패널" }).click();
  await expect(page.locator(".wire-inspector")).toBeVisible();
  const canvas = page.locator(".wire-canvas");
  await expect.poll(async () => {
    const frame = (await canvas.boundingBox())!;
    const panel = (await page.locator(".wire-inspector").boundingBox())!;
    return frame.x + frame.width - panel.x;
  }).toBeLessThanOrEqual(1);
  await expectCentered(page);
  await page.screenshot({ path: "test-results/workspace-centered-mobile-inspector.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".wire-inspector")).toBeVisible();
  await canvas.evaluate(element => { element.scrollLeft = 0; });
  await expect.poll(() => canvas.evaluate(element => element.querySelector(".wire-page")!.getBoundingClientRect().left - element.getBoundingClientRect().left)).toBeGreaterThanOrEqual(0);
  await canvas.evaluate(element => { element.scrollLeft = element.scrollWidth; });
  await expect.poll(() => canvas.evaluate(element => element.querySelector(".wire-page")!.getBoundingClientRect().right - element.getBoundingClientRect().right)).toBeLessThanOrEqual(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});

test("넘치는 시안은 왼쪽 시작과 오른쪽 끝까지 스크롤할 수 있다", async ({ page }) => {
  await setup(page, { documents: true });
  await page.getByRole("tab", { name: "화면 시안", exact: true }).click();
  await page.locator(".wire-thumbnail").first().click();
  await dragTo(page, 950);
  for (let i = 0; i < 4; i++) await page.getByRole("button", { name: "와이어프레임 확대" }).click();
  const canvas = page.locator(".wire-canvas");
  const edges = () => canvas.evaluate(element => {
    const content = element.querySelector(".wire-page")!.getBoundingClientRect();
    const frame = element.getBoundingClientRect();
    return { left: content.left - frame.left, right: content.right - frame.left, width: element.clientWidth };
  });
  await canvas.evaluate(element => { element.scrollLeft = 0; });
  await expect.poll(async () => (await edges()).left).toBeGreaterThanOrEqual(0);
  await canvas.evaluate(element => { element.scrollLeft = element.scrollWidth; });
  await expect.poll(async () => { const edge = await edges(); return edge.right - edge.width; }).toBeLessThanOrEqual(1);
});
