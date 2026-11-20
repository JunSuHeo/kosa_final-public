import { expect, test, type Page } from "@playwright/test";
import { begin, draft, login, readBundle } from "./business-helpers";
async function expectContained(page: Page) {
  await expect
    .poll(async () =>
      page.locator(".thumbnail-viewport").evaluateAll((frames) =>
        frames.every((frame) => {
          const screen = frame.querySelector<HTMLElement>(".wire-page")!;
          const fit = frame.querySelector<HTMLElement>(".thumbnail-fit")!;
          const outer = frame.getBoundingClientRect(),
            inner = screen.getBoundingClientRect();
          return (
            getComputedStyle(fit).visibility === "visible" &&
            inner.width > 0 &&
            inner.left >= outer.left + 11 &&
            inner.top >= outer.top + 11 &&
            inner.right <= outer.right - 11 &&
            inner.bottom <= outer.bottom - 11 &&
            inner.width <= screen.offsetWidth + 1
          );
        }),
      ),
    )
    .toBe(true);
}
test("흐름도의 모든 유형과 조작 UI는 밝고 목록 시안은 크기 변경 후에도 전체가 보인다", async ({
  page,
}) => {
  await login(page);
  const id = await begin(page);
  await draft(page);
  const bundle = await readBundle(page, id);
  const snapshot = structuredClone(bundle.proposal.candidate);
  const base = snapshot.screens[0];
  const block = base.blocks[0];
  snapshot.screens = [
    {
      ...base,
      id: "fit-short",
      title: "짧은 화면",
      blocks: [
        { ...block, type: "heading", label: "짧은 화면", content: "전체 표시" },
      ],
    },
    {
      ...base,
      id: "fit-long",
      title: "긴 화면",
      blocks: Array.from({ length: 12 }, (_, i) => ({
        ...block,
        id: `long-${i}`,
        type: "text",
        label: `업무 ${i + 1}`,
        content: "긴 업무 설명을 확인합니다. ".repeat(20),
      })),
    },
    {
      ...base,
      id: "fit-mobile",
      title: "모바일 화면",
      device: "mobile",
      blocks: [
        {
          ...block,
          type: "text",
          label: "모바일 안내",
          content: "작은 화면의 전체 높이도 맞춥니다.",
        },
      ],
    },
  ];
  const kinds = ["start", "screen", "action", "decision", "end"];
  snapshot.flow.nodes = kinds.map((type, i) => ({
    ...snapshot.flow.nodes[0],
    id: `light-${type}`,
    type,
    title: `밝은 ${type}`,
    x: (i % 3) * 280,
    y: Math.floor(i / 3) * 180,
  }));
  snapshot.flow.edges = kinds
    .slice(1)
    .map((_, i) => ({
      id: `light-edge-${i}`,
      source: `light-${kinds[i]}`,
      target: `light-${kinds[i + 1]}`,
      label: "업무 확인",
    }));
  bundle.proposal.candidate = snapshot;
  await page.route(`**/api/projects/${id}`, (route) =>
    route.fulfill({ json: bundle }),
  );
  await page.reload();
  await page.getByRole("tab", { name: "업무 흐름", exact: true }).click();
  await expect(page.locator(".react-flow")).toHaveClass(/light/);
  await expect(page.locator(".graph-canvas")).toHaveCSS(
    "background-color",
    "rgb(243, 246, 251)",
  );
  for (const kind of kinds) {
    const color =
      kind === "decision"
        ? "rgb(255, 248, 231)"
        : ["screen", "start", "end"].includes(kind)
          ? "rgb(234, 242, 255)"
          : "rgb(255, 255, 255)";
    await expect(page.locator(`.canvas-node.${kind}`)).toHaveCSS(
      "background-color",
      color,
    );
  }
  await expect(page.locator(".react-flow__controls-button").first()).toHaveCSS(
    "background-color",
    "rgb(255, 255, 255)",
  );
  await expect(page.locator(".react-flow__minimap")).toHaveCSS(
    "background-color",
    "rgb(255, 255, 255)",
  );
  await expect(page.locator(".react-flow__edge-textbg").first()).toHaveCSS(
    "fill",
    "rgb(255, 255, 255)",
  );
  await page.locator(".canvas-node.action").click();
  await expect(page.locator(".canvas-node.action")).toHaveCSS(
    "border-top-color",
    "rgb(37, 99, 235)",
  );
  await page.screenshot({
    path: "test-results/hplan-light-flow.png",
    fullPage: true,
  });
  await page.getByRole("tab", { name: "화면 시안", exact: true }).click();
  await expect(page.locator(".wire-thumbnail")).toHaveCount(3);
  await expectContained(page);
  await expect(page.locator(".thumbnail-viewport").first()).toHaveCSS(
    "height",
    "275px",
  );
  const before = await page
    .locator('[data-screen-id="fit-short"] .wire-page')
    .boundingBox();
  const handle = await page
    .getByRole("separator", { name: "대화와 산출물 너비 조절" })
    .boundingBox();
  await page.mouse.move(handle!.x + 4, 300);
  await page.mouse.down();
  await page.mouse.move(950, 300, { steps: 10 });
  await page.mouse.up();
  await expectContained(page);
  await expect
    .poll(
      async () =>
        (await page
          .locator('[data-screen-id="fit-short"] .wire-page')
          .boundingBox())!.width,
    )
    .not.toBe(before!.width);
  await page.screenshot({
    path: "test-results/hplan-fit-thumbnails.png",
    fullPage: true,
  });
  await page.locator(".wire-thumbnail").first().click();
  await expect(page.locator(".wire-single .wire-page")).toBeVisible();
  await page.getByRole("button", { name: "미리보기", exact: true }).click();
  await expect(page.locator(".preview-notice")).toBeVisible();
  await page.getByRole("button", { name: "전체 화면", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "산출물", exact: true }).click();
  await expectContained(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(
    390,
  );
  await page.setViewportSize({ width: 1600, height: 1000 });
  await expectContained(page);
});
