import { login } from "./business-helpers";
import { expect, test } from "./server-fixture";
test.beforeEach(async ({ page }) => {
  await login(page);
});
import {
  businessSource,
  begin,
  confirm,
  draft,
  readBundle,
} from "./business-helpers";

test("업무 연결 설정에서 소스 디자인·사용 범위를 확인해 게시한다", async ({
  page,
}) => {
  const repository = process.env.E2E_FIXTURE_REPO;
  test.skip(!repository, "Run scripts/e2e.sh to mount the isolated fixture.");
  await page.goto("/");
  await expect(
    page
      .locator(".business-header-actions")
      .getByRole("button", { name: "업무 연결 설정", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "관리자 메뉴 열기", exact: true })
    .click();
  await page
    .getByRole("navigation", { name: "관리자 메뉴", exact: true })
    .getByRole("button", { name: "업무 연결 설정", exact: true })
    .click();
  await page
    .getByRole("button", { name: "기준 프로젝트 등록", exact: true })
    .click();
  await page.getByLabel("이름", { exact: true }).fill("발주관리 업무");
  await page.getByLabel("저장소", { exact: true }).fill(repository!);
  await page
    .getByLabel("설명", { exact: true })
    .fill("발주 요청·승인·처리 내역을 관리합니다.");
  await page.getByRole("button", { name: "등록하고 분석" }).click();
  await expect(
    page.getByRole("heading", { name: "화면 디자인", exact: true }),
  ).toBeVisible({ timeout: 20000 });
  await expect(page.getByLabel("주요 버튼", { exact: true })).toHaveValue(
    "#0c7a6b",
  );
  await page.getByLabel("주요 버튼", { exact: true }).fill("#126c60");
  await page
    .getByRole("button", { name: "이 코드 범위와 디자인으로 준비" })
    .click();
  await page.getByRole("button", { name: "확인하고 업무 게시" }).click();
  await expect(page.getByRole("status")).toContainText("업무를 게시했어요");
  await page.screenshot({
    path: "test-results/hplan-settings.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "업무 선택으로 돌아가기" }).click();
  const source = await businessSource(page.request);
  await expect(
    page.locator(`.business-card[data-source-id="${source.id}"]`),
  ).toBeEnabled();
  await page.screenshot({
    path: "test-results/hplan-home.png",
    fullPage: true,
  });
});

test("게시된 코드·디자인 기준은 재접속과 확인본 내보내기에서 유지된다", async ({
  page,
}) => {
  await businessSource(page.request);
  const id = await begin(page);
  await draft(page);
  const before = await readBundle(page, id);
  await page.getByRole("tab", { name: "화면 시안", exact: true }).click();
  await page.locator(".wire-thumbnail").first().click();
  const color = before.proposal.candidate.design_profile.primary;
  await expect(page.locator(".wire-page .wire-button-surface")).toHaveCSS(
    "background-color",
    color === "#126c60" ? "rgb(18, 108, 96)" : "rgb(12, 122, 107)",
  );
  await page.screenshot({
    path: "test-results/hplan-workspace.png",
    fullPage: true,
  });
  await confirm(page);
  await page.reload();
  const after = await readBundle(page, id);
  expect(after.project.code_snapshot_id).toBe(before.project.code_snapshot_id);
  expect(after.revision.snapshot.design_profile).toEqual(
    before.proposal.candidate.design_profile,
  );
  await page.getByRole("button", { name: "내보내기" }).click();
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "문서 파일 (.md)", exact: true })
    .click();
  expect((await download).suggestedFilename()).toBe("studio-v1.md");
});

test("GitHub 승인 후 업무 연결 등록에서 비공개 저장소를 선택한다", async ({ page }) => {
  const state = "a".repeat(43);
  let connected = false;
  await page.route("**/api/sources/github", (route) => route.fulfill({
    json: { enabled: true, connected, login: connected ? "octo" : null, install_url: null },
  }));
  await page.route("**/api/sources/github/start", (route) => route.fulfill({
    json: { url: `https://github.com/login/oauth/authorize?state=${state}` },
  }));
  await page.route("https://github.com/login/oauth/authorize?*", (route) => route.fulfill({
    status: 302, headers: { location: new URL(`/github/callback?state=${state}&code=example`, page.url()).href },
  }));
  await page.route("**/api/sources/github/complete", (route) => {
    expect(route.request().postDataJSON()).toEqual({ state, code: "example" });
    connected = true;
    return route.fulfill({ json: { enabled: true, connected, login: "octo", install_url: null } });
  });
  await page.route("**/api/sources/github/repositories", (route) => route.fulfill({
    json: [{ name: "octo/private", branch: "trunk", private: true }],
  }));
  await page.route("**/api/sources/*/analyze", (route) => route.fulfill({
    json: { status: "queued" },
  }));
  await page.goto("/?view=settings");
  await page.getByRole("button", { name: "기준 프로젝트 등록" }).click();
  await page.getByLabel("연결 유형").selectOption("github");
  await page.getByLabel("이름", { exact: true }).fill("케이터링");
  await page.getByRole("button", { name: "GitHub 연결", exact: true }).click();
  await expect(page).toHaveURL(/\?view=settings$/);
  await expect(page.getByText("GitHub 연결됨 · octo")).toBeVisible();
  await expect(page.getByLabel("이름", { exact: true })).toHaveValue("케이터링");
  await page.getByLabel("연결한 GitHub 저장소").selectOption("octo/private");
  await expect(page.getByLabel("저장소", { exact: true })).toHaveValue("https://github.com/octo/private");
  await expect(page.getByLabel("브랜치", { exact: true })).toHaveValue("trunk");
  const registered = page.waitForRequest((request) =>
    request.method() === "POST" && new URL(request.url()).pathname === "/api/sources"
  );
  await page.getByRole("button", { name: "등록하고 분석" }).click();
  expect((await registered).postDataJSON()).toMatchObject({
    kind: "github", repository: "https://github.com/octo/private", ref: "trunk",
  });
  await expect(page.getByRole("button", { name: "기준 프로젝트 등록" })).toBeVisible();
  await page.getByRole("button", { name: "업무 선택으로 돌아가기" }).click();
  await page.getByRole("button", { name: "관리자 메뉴 열기" }).click();
  await page.getByRole("navigation", { name: "관리자 메뉴" })
    .getByRole("button", { name: "업무 연결 설정" }).click();
  await expect(page.getByRole("button", { name: "기준 프로젝트 등록" })).toBeVisible();
});
