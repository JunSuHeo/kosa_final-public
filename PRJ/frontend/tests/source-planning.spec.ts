import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";

test("registered repository planning retains its code basis through approval and download", async ({ page }) => {
  const repository = process.env.E2E_FIXTURE_REPO;
  test.skip(!repository, "Run scripts/e2e.sh to mount the fixture.");
  await page.goto("/");
  await page.getByText("기준 프로젝트 등록", { exact: true }).click();
  await page.getByLabel("이름", { exact: true }).fill(repository!);
  await page.getByLabel("저장소", { exact: true }).fill(repository!);
  await page.getByRole("button", { name: "등록하고 분석" }).click();
  await expect(page.getByText(`${repository} · 준비 완료`, { exact: true }).last()).toBeVisible({ timeout: 15000 });
  await page.reload();
  await expect(page.getByLabel("어떤 프로젝트를 기획할까요?")).not.toHaveValue("");
  await page.getByLabel("만들고 싶은 제품 아이디어").fill("Add an Enter keyboard shortcut for fixtureSearch");
  await page.getByRole("button", { name: "코드 범위 확인", exact: true }).click();
  const preview = page.getByRole("region", { name: "전달할 코드 범위" });
  await preview.getByText(/search.ts:1/).click();
  await expect(preview.getByText(/export function fixtureSearch/)).toBeVisible();
  await preview.getByRole("button", { name: "코드 범위 확인하고 기획 시작" }).click();
  await expect(page.getByText("변경 정책의 범위를 어디까지 적용할까요?")).toBeVisible({ timeout: 15000 });
  await page.getByRole("button", { name: "요청한 기능만" }).click();
  await page.getByRole("button", { name: "기획 시작", exact: true }).click();
  await expect(page.getByRole("button", { name: "검토 중인 초안" })).toBeVisible({ timeout: 20000 });
  await page.getByRole("tab", { name: "구현 지침" }).click();
  await expect(page.getByRole("heading", { name: "수용 테스트" })).toBeVisible();
  await page.getByRole("button", { name: "검토", exact: true }).click();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: /승인/ }).click();
  await expect(page.getByRole("button", { name: "확정본 v1" })).toBeVisible();
  await page.reload();
  const basis = page.locator(".workspace-source");
  await expect(basis.getByText(repository!, { exact: true })).toBeVisible();
  const commit = await basis.locator("code").first().innerText();
  await page.getByRole("button", { name: "최신 코드 확인" }).click();
  await expect(page.getByText("현재 기준과 동일")).toBeVisible();
  await page.getByRole("button", { name: "내보내기" }).click();
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Markdown (.md)" }).click(),
  ]);
  const markdown = await readFile((await download.path())!, "utf8");
  expect(markdown).toContain(commit);
  expect(markdown).toContain("fixtureSearch");
  expect(markdown).toContain("미커밋 변경");
  await page.getByRole("tab", { name: "구현 지침" }).click();
  await page.getByRole("button", { name: "직접 편집" }).click();
  await page.getByLabel("변경 후 동작", { exact: true }).fill("승인 전까지 기존 기획을 유지하는 수정");
  await page.getByRole("button", { name: "수정안 검토" }).click();
  await expect(page.getByRole("button", { name: "검토 중인 초안" })).toBeVisible();
  await expect(page.getByRole("button", { name: "확정본 v1" })).toBeVisible();
  await expect(basis.locator("code").first()).toHaveText(commit);
});

test("source controls fit the dark composer beside long project cards on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/projects", (route) => route.fulfill({
    json: [{
      id: "41d49922-0171-465e-b704-1673e5528642",
      title: "긴프로젝트제목".repeat(20),
      idea: "저장소를기준으로긴기능요청을입력합니다".repeat(20),
      source_id: null,
      current_version: 0,
      updated_at: new Date().toISOString(),
    }],
  }));
  await page.goto("/");
  await expect(page.locator(".project-card")).toBeVisible();
  const composer = page.locator(".planning-composer");
  await expect(composer.getByLabel("어떤 프로젝트를 기획할까요?")).toHaveCSS("color-scheme", "dark");
  const register = composer.getByRole("button", { name: "기준 프로젝트 등록" });
  await register.focus();
  await page.keyboard.press("Enter");
  await expect(composer.getByLabel("저장소", { exact: true })).toBeVisible();
  await expect(composer.getByLabel("저장소", { exact: true })).toHaveCSS("background-color", "rgb(32, 32, 37)");
  const widths = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  expect(widths[0]).toBe(widths[1]);
  await composer.getByRole("button", { name: "등록 닫기" }).click();
  await expect(composer.getByLabel("저장소", { exact: true })).toBeHidden();
});

test("초안 보기가 비어 있는 기능 탭에서 생성된 구현 지침을 연다", async ({ page }) => {
  const id = "00000000-0000-4000-8000-000000000123";
  const now = "2026-11-11T00:00:00Z";
  const sourceContext = {
    source_id: id, snapshot_id: id, name: "테스트 저장소", repository: "fixture",
    ref: "main", commit_sha: "a".repeat(40), analysis_version: "1",
    files_analyzed: 1, analysis_paths: [], excluded: {}, evidence: [],
  };
  const snapshot = {
    prd: { title: "월별 집계", sections: [], roles: [], platforms: [], assumptions: [] },
    requirements: [], features: [], flow: { nodes: [], edges: [] },
    screens: [], source_context: sourceContext,
  };
  const revision = { version: 0, summary: "프로젝트 시작", created_at: now };
  await page.route("**/api/projects/" + id, (route) => route.fulfill({ json: {
    project: { id, title: "월별 집계", current_version: 0, source_id: id },
    revision: { ...revision, snapshot },
    revisions: [revision],
    job: null,
    messages: [],
    proposal: {
      id: "partial-draft", base_version: 0, summary: "초안",
      candidate: { ...snapshot, implementation: {
        current_behavior: "일별 근무기록을 표시한다.",
        proposed_behavior: "기존 근무대장에 월별 집계 탭을 추가한다.",
        confirmed_policy: [], preserve: [], exceptions: [], assumptions: [],
        unresolved: [], scope: [], tasks: [], acceptance: [],
      } },
      issues: [{ severity: "blocking", target: "snapshot", message: "PRD가 필요합니다." }],
      diff: [],
    },
  } }));
  await page.goto("/?project=" + id);
  await page.getByRole("tab", { name: "기능명세서" }).click();
  await page.getByRole("button", { name: "생성된 초안 보기" }).click();
  await expect(page.getByRole("tab", { name: "구현 지침" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByText("기존 근무대장에 월별 집계 탭을 추가한다.")).toBeVisible();
  await page.getByRole("button", { name: "검토", exact: true }).click();
  await expect(page.getByRole("button", { name: "승인하고 확정" })).toBeDisabled();
});
