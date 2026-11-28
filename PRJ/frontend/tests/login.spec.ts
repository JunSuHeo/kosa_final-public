import { expect, test } from "./server-fixture";
import { login } from "./business-helpers";
import { headers } from "./server-fixture";
const password = "a123456789!";

test.beforeEach(async ({ request }) => {
  const health = await (await request.get("/health")).json();
  expect(health.auth_mode).toBe("supabase");
  expect(health.ai_mode).toBe("mock");
});

test("로그인 전에는 계정과 업무 데이터를 표시하지 않고 빈 입력을 막는다", async ({
  page,
}) => {
  const privateCalls: string[] = [];
  page.on("request", (request) => {
    if (/\/api\/(projects|sources)/.test(request.url()))
      privateCalls.push(request.url());
  });
  await page.goto("/");
  const form = page.getByRole("form", { name: "로그인", exact: true });
  await expect(form).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "업무 기획을 시작해 보세요" }),
  ).toBeVisible();
  await expect(form.locator(".login-emblem")).toHaveCount(0);
  await expect(form).not.toContainText("테스트 환경");
  await expect(form).not.toContainText("admin");
  await expect(form).not.toContainText(password);
  await expect(page.getByLabel("아이디", { exact: true })).toHaveValue("");
  await expect(page.getByLabel("비밀번호", { exact: true })).toHaveValue("");
  await page.screenshot({
    path: "test-results/hplan-login-desktop.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  expect(
    await page
      .getByLabel("아이디", { exact: true })
      .evaluate((input) => (input as HTMLInputElement).validity.valueMissing),
  ).toBeTruthy();
  await expect(
    page.getByRole("heading", { name: "어떤 업무를 기획하시겠어요?" }),
  ).toHaveCount(0);
  expect(privateCalls).toEqual([]);
});

test("오입력은 ID를 유지하고 비밀번호를 지우며 표시 전환·Enter 로그인을 지원한다", async ({
  page,
}) => {
  await page.goto("/");
  const id = page.getByLabel("아이디", { exact: true });
  const pw = page.getByLabel("비밀번호", { exact: true });
  await id.fill("wrong");
  await pw.fill(password);
  await page
    .getByRole("button", { name: "비밀번호 보기", exact: true })
    .click();
  await expect(pw).toHaveAttribute("type", "text");
  await page
    .getByRole("button", { name: "비밀번호 숨기기", exact: true })
    .click();
  await expect(pw).toHaveAttribute("type", "password");
  await pw.press("Enter");
  await expect(page.getByRole("alert")).toContainText(
    "ID 또는 비밀번호를 확인해 주세요",
  );
  await expect(id).toHaveValue("wrong");
  await expect(pw).toHaveValue("");
  await expect(pw).toBeFocused();
  await id.fill(" admin ");
  await pw.fill(password + " ");
  await pw.press("Enter");
  await expect(page.getByRole("alert")).toContainText(
    "ID 또는 비밀번호를 확인해 주세요",
  );
  await pw.fill(password);
  await pw.press("Enter");
  await expect(
    page.getByRole("heading", { name: "어떤 업무를 기획하시겠어요?" }),
  ).toBeVisible();
  const freshTab = await page.context().newPage();
  await freshTab.goto("/");
  await expect(
    freshTab.getByRole("form", { name: "로그인", exact: true }),
  ).toBeVisible();
  await freshTab.close();
  const storage = await page.evaluate(() =>
    JSON.stringify({
      session: { ...sessionStorage },
      local: { ...localStorage },
    }),
  );
  expect(storage).not.toContain(password);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "어떤 업무를 기획하시겠어요?" }),
  ).toBeVisible();
});

test("모바일 로그인과 로그아웃 후 직접 프로젝트 주소 재진입을 확인한다", async ({
  page,
  request,
}) => {
  const created = await request.post("/api/projects", {
    headers,
    data: {
      id: crypto.randomUUID(),
      idea: "로그인 후 이어서 볼 테스트 기획",
      title: "로그인 복귀 확인",
    },
  });
  expect(created.ok()).toBeTruthy();
  const project = await created.json();
  const bundle = await (
    await request.get(`/api/projects/${project.id}`, { headers })
  ).json();
  if (["queued", "running", "awaiting_answers"].includes(bundle.job?.status))
    await request.post(
      `/api/projects/${project.id}/jobs/${bundle.job.id}/cancel`,
      { headers, data: {} },
    );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/?project=${project.id}`);
  const form = page.getByRole("form", { name: "로그인", exact: true });
  await expect(form).toBeVisible();
  await expect(
    form.getByRole("heading", { name: "업무 기획을 시작해 보세요" }),
  ).toBeVisible();
  await expect(form.locator(".login-emblem")).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(
    390,
  );
  await page.screenshot({
    path: "test-results/hplan-login-mobile.png",
    fullPage: true,
  });
  await page.getByLabel("아이디", { exact: true }).fill("admin");
  await page.getByLabel("비밀번호", { exact: true }).fill(password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page.getByLabel("기획 도구")).toBeVisible();
  await expect(page).toHaveURL(new RegExp(project.id));
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(
    390,
  );
  await page
    .getByLabel("계정 메뉴", { exact: true })
    .filter({ visible: true })
    .click();
  await page.getByRole("button", { name: "로그아웃", exact: true }).click();
  await expect(
    page.getByRole("form", { name: "로그인", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => sessionStorage.getItem("studio-token")),
  ).toBeNull();
  await page.goto(`/?project=${project.id}`);
  await expect(
    page.getByRole("form", { name: "로그인", exact: true }),
  ).toBeVisible();
  await login(page);
  await page.getByLabel("계정 메뉴", { exact: true }).click();
  await page.getByRole("button", { name: "로그아웃", exact: true }).click();
  await expect(
    page.getByRole("form", { name: "로그인", exact: true }),
  ).toBeVisible();
});

test("기존 자동 진입 토큰만 남은 탭도 테스트 로그인을 요구한다", async ({
  page,
}) => {
  await page.addInitScript(() => {
    sessionStorage.setItem("studio-token", "local:demo-user");
  });
  await page.goto("/?view=settings");
  await expect(
    page.getByRole("form", { name: "로그인", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "업무 연결 설정", exact: true }),
  ).toHaveCount(0);
});
