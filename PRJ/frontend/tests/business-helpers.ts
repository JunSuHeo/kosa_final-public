import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { headers } from "./server-fixture";
export async function login(
  page: Page,
  path = "/",
  identifier = "admin",
  password = "a123456789!",
) {
  await page.goto(path);
  await expect(
    page.getByRole("form", { name: "로그인", exact: true }),
  ).toBeVisible();
  await page.getByLabel("아이디", { exact: true }).fill(identifier);
  await page.getByLabel("비밀번호", { exact: true }).fill(password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(
    page.getByRole("form", { name: "로그인", exact: true }),
  ).toHaveCount(0);
}
export async function businessSource(request: APIRequestContext) {
  const repository = process.env.E2E_FIXTURE_REPO;
  if (!repository)
    throw new Error("Run scripts/e2e.sh with the isolated repository fixture.");
  let sources = await (await request.get("/api/sources", { headers })).json();
  let source = sources.find(
    (item: { repository: string }) => item.repository === repository,
  );
  if (!source) {
    const response = await request.post("/api/sources", {
      headers,
      data: {
        name: "발주관리 업무",
        description: "발주 요청·승인·처리 내역을 관리합니다.",
        kind: "local",
        repository,
        ref: "HEAD",
      },
    });
    expect(response.ok()).toBeTruthy();
    source = await response.json();
  }
  if (!source.publication_id) {
    const snapshot = await (
      await request.post(`/api/sources/${source.id}/analyze`, {
        headers,
        data: {},
      })
    ).json();
    await expect
      .poll(
        async () =>
          (
            await (
              await request.get(
                `/api/sources/${source.id}/snapshots/${snapshot.id}`,
                { headers },
              )
            ).json()
          ).status,
      )
      .toBe("ready");
    const preview = await (
      await request.post(
        `/api/sources/${source.id}/snapshots/${snapshot.id}/publication-preview`,
        { headers, data: {} },
      )
    ).json();
    const response = await request.post(`/api/sources/${source.id}/publish`, {
      headers,
      data: {
        snapshot_id: snapshot.id,
        fingerprint: preview.fingerprint,
        design_profile: preview.design_profile,
      },
    });
    expect(response.ok()).toBeTruthy();
    sources = await (await request.get("/api/sources", { headers })).json();
    source = sources.find((item: { id: string }) => item.id === source.id);
  }
  return source;
}
export async function begin(page: Page) {
  const source = await businessSource(page.request);
  await page.goto("/");
  await page.locator(`.business-card[data-source-id="${source.id}"]`).click();
  await page
    .getByLabel("업무 설명", { exact: true })
    .fill(
      "발주 담당자가 주문을 확인한 뒤 승인하도록 개선하고 싶어요. " +
        Date.now(),
    );
  await page.getByRole("button", { name: "업무 대화 시작" }).click();
  await expect(page).toHaveURL(/project=/);
  await expect(page.locator(".draft-action")).toBeEnabled();
  return new URL(page.url()).searchParams.get("project")!;
}
export async function draft(page: Page) {
  const id = new URL(page.url()).searchParams.get("project")!;
  const previous = (await readBundle(page, id)).proposal?.id;
  await page.locator(".draft-action").click();
  await expect
    .poll(
      async () => {
        const current = await readBundle(page, id);
        return (
          current.job?.status === "waiting_review" &&
          !!current.proposal &&
          current.proposal.id !== previous
        );
      },
      { timeout: 20000 },
    )
    .toBeTruthy();
  const current = await readBundle(page, id);
  await expect(page.locator(".review-chat-card")).toHaveAttribute(
    "data-proposal-id",
    current.proposal.id,
    { timeout: 20000 },
  );
}
export async function confirm(page: Page) {
  await page.locator(".review-chat-card").click();
  const ack = page.getByRole("checkbox", {
    name: "위 확인 사항과 가정을 살펴봤어요",
  });
  if (await ack.count()) await ack.check();
  await page
    .getByRole("button", { name: "현업 확인본 저장", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "현업 확인본 저장", exact: true }),
  ).toHaveCount(0);
}
export async function readBundle(page: Page, id: string) {
  return (await page.request.get(`/api/projects/${id}`, { headers })).json();
}
