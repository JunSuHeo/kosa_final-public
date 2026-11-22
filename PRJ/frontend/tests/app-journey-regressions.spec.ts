import { test, expect, type Page } from "@playwright/test";

const A = "11111111-1111-4111-8111-111111111111";
const B = "22222222-2222-4222-8222-222222222222";
const owner = "journey-owner";
const source = { id: "business-source", name: "발주 업무", description: "발주 개선", publication_id: "published", published_snapshot_id: "code", published_model: null };
const snapshot = (text = "기존 업무") => ({ prd: { title: "발주 업무", roles: [], platforms: [], assumptions: [], sections: [{ id: "goal", title: "제품 목표", group: "개요", content: text }] }, requirements: [], features: [], flow: { nodes: [], edges: [] }, screens: [] });
const brief = { current_work: "발주", problem: "대기", desired_change: "승인", actors: [], rules: [], exceptions: [], confirmed_facts: [], user_statements: [], open_questions: [] };
const question = { key: "decision", title: "승인 담당자는 누구인가요?", options: ["팀장", "담당자"] };
function data(id: string, empty = false) {
  const value = snapshot();
  if (empty) value.prd.sections = [];
  return { project: { id, source_id: source.id, title: id === B ? "다른 업무" : "발주 업무", idea: "발주 승인 개선", current_version: empty ? 0 : 1, updated_at: new Date().toISOString(), conversation_brief: brief }, revision: { version: empty ? 0 : 1, snapshot: value }, proposal: null as any, job: null as any, messages: [], revisions: [], screen_previews: [] };
}
async function setup(page: Page, options: { pending?: boolean; empty?: boolean; questions?: boolean } = {}) {
  const all: Record<string, ReturnType<typeof data>> = { [A]: data(A, options.empty), [B]: data(B) };
  if (options.pending) all[A].proposal = { id: "pending", base_version: all[A].project.current_version, candidate: snapshot("작성 중인 개선안"), issues: [{ severity: "blocking", target: "prd", message: "연결 확인 필요" }], diff: [], summary: "개선안" };
  if (options.questions) all[A].job = { id: "discussion", kind: "discuss", status: "completed", stage: "done", partial: { discussion: { reply: "정리했어요", questions: [question] } }, questions: [], base_version: all[A].project.current_version };
  const state = { all, creates: [] as any[], jobs: [] as any[], answers: [] as any[], saves: [] as any[], failList: false, failDetail: false, abortCreate: false, abortJob: false, holdSave: null as null | Promise<void>, holdJob: null as null | Promise<void>, holdDecision: null as null | Promise<void>, decisionStarted: false, saveStarted: false };
  const permissions = ["plans.read", "plans.create", "plans.edit", "plans.confirm", "plans.export"];
  const identity = { account: { id: owner, loginId: "worker", name: "담당자", role: "USER1", active: true }, policy: { USER1: Object.fromEntries(permissions.map(p => [p, true])) } };
  await page.route("**/health", route => route.fulfill({ json: { auth_mode: "supabase", ai_mode: "mock", status: "ok" } }));
  await page.route("**/api/**", async route => {
    const req = route.request(), path = new URL(req.url()).pathname;
    if (path === "/api/auth/login") return route.fulfill({ json: { access_token: "fixture", refresh_token: "refresh", expires_in: 3600, identity } });
    if (path === "/api/auth/me") return route.fulfill({ json: identity });
    if (path === "/api/sources") return route.fulfill({ json: [source] });
    if (path === "/api/projects" && req.method() === "POST") {
      const body = req.postDataJSON(); state.creates.push(body); state.all[body.id] = data(body.id, true);
      if (state.abortCreate) { state.abortCreate = false; return route.abort("failed"); }
      return route.fulfill({ json: state.all[body.id].project });
    }
    if (path === "/api/projects") return state.failList ? route.fulfill({ status: 503, json: { detail: "목록을 다시 불러와 주세요" } }) : route.fulfill({ json: Object.values(all).map(x => x.project) });
    const match = path.match(/^\/api\/projects\/([^/]+)(.*)$/);
    if (match) {
      const [, id, tail] = match;
      if (tail === "/jobs" && req.method() === "POST") {
        state.jobs.push(req.postDataJSON());
        if (state.holdJob) await state.holdJob;
        if (state.abortJob) { state.abortJob = false; return route.abort("failed"); }
        return route.fulfill({ json: { id: req.postDataJSON().id, kind: req.postDataJSON().kind, status: "queued", stage: "prd", questions: [], partial: {}, base_version: 1 } });
      }
      if (tail.endsWith("/answers")) {
        state.answers.push(req.postDataJSON());
        return route.fulfill({ json: { ...all[id].job, status: "queued" } });
      }
      if (tail.endsWith("/approve") || tail.endsWith("/reject")) {
        state.decisionStarted = true;
        if (state.holdDecision) await state.holdDecision;
        return route.fulfill({ json: { status: "approved", version: 2 } });
      }
      if (tail === "/proposals" && req.method() === "POST") {
        state.saves.push(req.postDataJSON()); state.saveStarted = true;
        if (state.holdSave) await state.holdSave;
        return route.fulfill({ json: { id: "saved" } });
      }
      if (!tail) return state.failDetail ? route.fulfill({ status: 503, json: { detail: "기획 조회를 다시 시도해 주세요" } }) : route.fulfill({ json: all[id] });
      if (tail.includes("/reviews")) return route.fulfill({ json: null });
    }
    return route.fulfill({ json: [] });
  });
  await page.goto(`/?project=${A}`);
  await page.getByLabel("아이디", { exact: true }).fill("worker");
  await page.getByLabel("비밀번호", { exact: true }).fill("fixture-password");
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page.getByRole("button", { name: "현업 확인본 v1", exact: true }).or(page.getByRole("button", { name: "작성 중인 초안", exact: true })).first()).toBeVisible();
  return state;
}

test("확인본에서 직접 편집하여 보관 중인 초안을 덮어쓸 수 없다", async ({ page }) => {
  const state = await setup(page, { pending: true });
  await page.getByRole("button", { name: "현업 확인본 v1", exact: true }).click();
  await expect(page.getByRole("button", { name: "직접 편집", exact: true })).toBeDisabled();
  await expect(page.getByText("작성 중인 초안을 선택한 뒤 편집해 주세요.", { exact: true })).toBeVisible();
  expect(state.saves).toHaveLength(0);
});

test("확인본이 비어 있어도 보관 중인 초안의 검토 도구를 유지한다", async ({ page }) => {
  await setup(page, { pending: true, empty: true });
  await page.getByRole("button", { name: "아직 확인본이 없어요", exact: true }).click();
  await expect(page.getByRole("button", { name: "내용 확인", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "내용 확인", exact: true }).click();
  await expect(page.locator(".business-review")).toContainText("작성 중인 개선안");
});

test("프로젝트 생성 응답이 유실되어도 같은 입력의 재시도는 같은 ID를 사용한다", async ({ page }) => {
  const state = await setup(page);
  await page.getByRole("button", { name: "프로젝트 목록", exact: true }).click();
  await page.locator(".business-card").click();
  await page.getByLabel("업무 설명", { exact: true }).fill("발주 승인을 개선해 주세요.");
  state.abortCreate = true;
  await page.getByRole("button", { name: "업무 대화 시작", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "업무 대화 시작", exact: true }).click();
  await expect.poll(() => state.creates.length).toBe(2);
  expect(state.creates[1]).toEqual(state.creates[0]);
});

test("생성 POST 성공은 목록 조회 실패와 구분하고 입력을 다시 제출하게 하지 않는다", async ({ page }) => {
  const state = await setup(page);
  await page.getByRole("button", { name: "프로젝트 목록", exact: true }).click();
  await page.locator(".business-card").click();
  await page.getByLabel("업무 설명", { exact: true }).fill("발주 승인 개선 요청입니다.");
  state.failList = true;
  await page.getByRole("button", { name: "업무 대화 시작", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`project=${state.creates[0]?.id || "[a-f0-9-]+"}`));
  await expect(page.getByLabel("업무 설명", { exact: true })).toHaveCount(0);
  expect(state.creates).toHaveLength(1);
});

test("대화 POST 성공 후 조회가 실패해도 이미 보낸 입력을 비운다", async ({ page }) => {
  const state = await setup(page);
  await page.getByLabel("업무 대화 입력").fill("승인자는 팀장입니다.");
  state.failDetail = true;
  await page.getByRole("button", { name: "업무 대화 보내기", exact: true }).click();
  await expect(page.getByLabel("업무 대화 입력")).toHaveValue("");
  expect(state.jobs).toHaveLength(1);
});

test("이전 프로젝트의 편집 저장 응답은 현재 프로젝트의 복원된 편집을 닫지 않는다", async ({ page }) => {
  const state = await setup(page);
  await page.getByRole("button", { name: "직접 편집", exact: true }).click();
  await page.getByLabel("제품 목표 편집").fill("A에서 편집한 내용");
  let release!: () => void;
  state.holdSave = new Promise<void>(resolve => { release = resolve; });
  await page.getByRole("button", { name: "수정 내용 확인", exact: true }).click();
  await expect.poll(() => state.saveStarted).toBe(true);
  await page.evaluate(({ owner, B, saved }) => sessionStorage.setItem(`hplan-tab-draft.v1:${owner}:edit:${B}`, JSON.stringify(saved)), { owner, B, saved: { baseVersion: 1, proposalId: null, candidate: false, snapshot: snapshot("B에서 이어 쓰는 내용") } });
  await page.getByRole("button", { name: "프로젝트 목록", exact: true }).click();
  await page.locator(".project-card").filter({ hasText: "다른 업무" }).click();
  await expect(page.getByLabel("제품 목표 편집")).toHaveValue("B에서 이어 쓰는 내용");
  release();
  await expect(page.getByRole("button", { name: "수정 내용 확인", exact: true })).toBeEnabled();
  await expect(page.getByLabel("제품 목표 편집")).toHaveValue("B에서 이어 쓰는 내용");
});

test("검토 화면으로 재진입해도 보관된 질문 답변을 보내기 전에 생성할 수 없다", async ({ page }) => {
  const state = await setup(page, { pending: true, questions: true });
  await page.evaluate(({ owner, A }) => sessionStorage.setItem(`hplan-tab-draft.v1:${encodeURIComponent(owner + ":" + A)}:dialogue:discussion:decision`, JSON.stringify({ choice: "custom", custom: "담당자에게 확인 중", sent: false })), { owner, A });
  await page.reload();
  await page.getByRole("button", { name: "AI로 정리하기", exact: true }).click();
  await expect(page.getByLabel("질문 직접 답변")).toHaveValue("담당자에게 확인 중");
  expect(state.jobs).toHaveLength(0);
});

test("브라우저 뒤로 가기는 검토 패널 대신 질문 대기 대화를 다시 연다", async ({ page }) => {
  const state = await setup(page);
  state.all[A].job = { id: "waiting", kind: "generate", status: "awaiting_answers", stage: "prd", partial: {}, questions: [question], base_version: 1 };
  await page.reload();
  await expect(page.locator(".question-card")).toBeVisible();
  await page.getByRole("button", { name: "프로젝트 목록", exact: true }).click();
  await page.locator(".project-card").filter({ hasText: "다른 업무" }).click();
  await page.getByRole("button", { name: "내용 확인", exact: true }).click();
  await page.goBack(); await page.goBack();
  await expect(page.locator(".question-card")).toBeVisible();
});


test("질문 답변 POST 성공 후 조회가 실패해도 질문을 다시 제출하지 않는다", async ({ page }) => {
  const state = await setup(page);
  state.all[A].job = { id: "waiting", kind: "generate", status: "awaiting_answers", stage: "prd", partial: {}, questions: [question], base_version: 1 };
  await page.reload();
  await page.locator(".question-card").getByRole("button", { name: "팀장", exact: true }).click();
  state.failDetail = true;
  await page.getByRole("button", { name: "기획 시작", exact: true }).click();
  await expect(page.locator(".question-card")).toHaveCount(0);
  await expect(page.locator(".generation-progress")).toBeVisible();
  expect(state.answers).toHaveLength(1);
});

test("초안 생성 응답이 유실되면 재시도에 같은 작업 ID와 요청을 사용한다", async ({ page }) => {
  const state = await setup(page);
  state.abortJob = true;
  await page.locator(".draft-action").click();
  await expect(page.getByRole("alert")).toBeVisible();
  await page.reload();
  await page.locator(".draft-action").click();
  await expect.poll(() => state.jobs.length).toBe(2);
  expect(state.jobs[1]).toEqual(state.jobs[0]);
});


for (const newer of [false, true]) {
  test(newer ? "전송 중 재진입해서 새로 쓴 입력은 이전 전송 성공이 지우지 않는다" : "전송 중 홈으로 이동해도 성공한 입력은 재진입 때 남지 않는다", async ({ page }) => {
    const state = await setup(page);
    let release!: () => void;
    state.holdJob = new Promise<void>(resolve => { release = resolve; });
    await page.getByLabel("업무 대화 입력").fill("서버에 보낼 승인 담당자 설명입니다.");
    const response = page.waitForResponse(res => res.request().method() === "POST" && res.url().endsWith("/jobs"));
    await page.getByRole("button", { name: "업무 대화 보내기", exact: true }).click();
    await expect.poll(() => state.jobs.length).toBe(1);
    await page.getByRole("button", { name: "프로젝트 목록", exact: true }).click();
    await expect(page.locator(".business-home")).toBeVisible();
    const reopen = () => page.locator(".project-card").filter({ hasText: "발주 업무" }).click();
    if (newer) {
      await reopen();
      await page.getByLabel("업무 대화 입력").fill("이후에 새로 적고 있는 예외 처리 설명입니다.");
    }
    const storedInput = () => page.evaluate(({ owner, A }) => sessionStorage.getItem(`hplan-tab-draft.v1:${encodeURIComponent(owner + ":" + A)}:chat:input`), { owner, A });
    await expect.poll(storedInput).toBe(JSON.stringify(newer ? "이후에 새로 적고 있는 예외 처리 설명입니다." : "서버에 보낼 승인 담당자 설명입니다."));
    release();
    await response;
    if (!newer) {
      await expect.poll(storedInput).not.toBe(JSON.stringify("서버에 보낼 승인 담당자 설명입니다."));
      await reopen();
    }
    if (newer) await expect(page.getByRole("button", { name: "업무 대화 보내기", exact: true })).toBeEnabled();
    await expect(page.getByLabel("업무 대화 입력")).toHaveValue(newer ? "이후에 새로 적고 있는 예외 처리 설명입니다." : "");
    expect(state.jobs).toHaveLength(1);
  });
}


test("이전 프로젝트 승인 응답은 현재 프로젝트에 복원한 편집을 닫지 않는다", async ({ page }) => {
  const state = await setup(page, { pending: true });
  state.all[A].proposal.issues = [];
  await page.reload();
  let release!: () => void;
  state.holdDecision = new Promise<void>(resolve => { release = resolve; });
  await page.getByRole("button", { name: "현업 확인본 저장", exact: true }).click();
  await expect.poll(() => state.decisionStarted).toBe(true);
  await page.evaluate(({ owner, B, saved }) => sessionStorage.setItem(`hplan-tab-draft.v1:${owner}:edit:${B}`, JSON.stringify(saved)), { owner, B, saved: { baseVersion: 1, proposalId: null, candidate: false, snapshot: snapshot("B에서 이어 쓰는 승인 기준") } });
  await page.getByRole("button", { name: "프로젝트 목록", exact: true }).click();
  await page.locator(".project-card").filter({ hasText: "다른 업무" }).click();
  await expect(page.getByLabel("제품 목표 편집")).toHaveValue("B에서 이어 쓰는 승인 기준");
  release();
  await expect(page.getByRole("button", { name: "수정 내용 확인", exact: true })).toBeEnabled();
  await expect(page.getByLabel("제품 목표 편집")).toHaveValue("B에서 이어 쓰는 승인 기준");
});

async function failedGeneration(page: Page) {
  const state = await setup(page);
  state.all[A].job = { id: "failed-original", kind: "generate", status: "failed", stage: "prd", partial: { target_id: "goal" }, questions: [], base_version: 1, base_proposal_id: null, request: "승인 담당자와 반려 절차를 정리해 주세요.", error: "일시적인 생성 오류" };
  await page.reload();
  await expect(page.getByRole("button", { name: "다시 시도", exact: true })).toBeVisible();
  return state;
}

test("실패 작업 재시도 응답이 유실되어도 같은 ID와 payload를 다시 보낸다", async ({ page }) => {
  const state = await failedGeneration(page);
  state.abortJob = true;
  await page.getByRole("button", { name: "다시 시도", exact: true }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "다시 시도", exact: true }).click();
  await expect.poll(() => state.jobs.length).toBe(2);
  expect(state.jobs[1]).toEqual(state.jobs[0]);
  expect(state.jobs[1]).toMatchObject({ kind: "generate", target_id: "goal", request: state.all[A].job.request });
});

test("실패 작업 재시도가 수락되면 후속 조회 실패에도 다시 제출하지 않는다", async ({ page }) => {
  const state = await failedGeneration(page);
  state.failDetail = true;
  await page.getByRole("button", { name: "다시 시도", exact: true }).click();
  await expect(page.getByRole("button", { name: "다시 시도", exact: true })).toHaveCount(0);
  await expect(page.locator(".generation-progress")).toBeVisible();
  expect(state.jobs).toHaveLength(1);
});

test("새로 입력한 내용을 보내기 전에는 실패한 생성 작업을 재시도할 수 없다", async ({ page }) => {
  const state = await failedGeneration(page);
  await page.getByLabel("업무 대화 입력").fill("예외 처리에 추가로 반영할 내용입니다.");
  await expect(page.getByRole("button", { name: "다시 시도", exact: true })).toBeDisabled();
  await expect(page.getByText("입력한 내용을 먼저 보내면 초안에 반영할 수 있어요.", { exact: true })).toBeVisible();
  expect(state.jobs).toHaveLength(0);
});

test("재시도 진입점은 Chat 상태에 없는 저장된 질문 초안도 확인한다", async ({ page }) => {
  const state = await failedGeneration(page);
  state.all[A].job.partial.discussion = { questions: [question] };
  await page.reload();
  await page.evaluate(({ owner, A }) => sessionStorage.setItem(`hplan-tab-draft.v1:${encodeURIComponent(owner + ":" + A)}:dialogue:failed-original:decision`, JSON.stringify({ choice: "custom", custom: "승인자를 아직 확인 중입니다.", sent: false })), { owner, A });
  await page.getByRole("button", { name: "다시 시도", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("입력한 내용을 먼저 보내 주세요.");
  expect(state.jobs).toHaveLength(0);
});
