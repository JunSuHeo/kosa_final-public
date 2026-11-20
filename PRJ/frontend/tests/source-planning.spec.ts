import { login } from "./business-helpers";
import { expect, test } from "@playwright/test";
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
  await page
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
    .getByRole("button", { name: "Markdown (.md)", exact: true })
    .click();
  expect((await download).suggestedFilename()).toBe("studio-v1.md");
});
