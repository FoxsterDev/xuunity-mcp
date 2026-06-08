import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type TestInfo } from "@playwright/test";

const README_URL = "https://github.com/FoxsterDev/xuunity-mcp/blob/master/README.md";

async function collectVisibleOverflow(page: Page) {
  return page.evaluate(() => {
    const clientWidth = document.documentElement.clientWidth;

    return Array.from(document.querySelectorAll("body *"))
      .map((element) => {
        const rect = element.getBoundingClientRect();
        if (!rect.width || !rect.height) return null;
        if (rect.right <= clientWidth + 1 && rect.left >= -1) return null;

        return {
          tag: element.tagName.toLowerCase(),
          className: String(element.getAttribute("class") ?? "").slice(0, 80),
          text: String(element.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 100),
          rect: [Math.round(rect.left), Math.round(rect.top), Math.round(rect.right), Math.round(rect.bottom)]
        };
      })
      .filter(Boolean);
  });
}

async function attachPageScreenshots(page: Page, testInfo: TestInfo, label: string) {
  await testInfo.attach(`${label}-viewport`, {
    body: await page.screenshot({ fullPage: false }),
    contentType: "image/png"
  });
  await testInfo.attach(`${label}-full-page`, {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png"
  });
}

test.describe("public homepage", () => {
  test("keeps the product story, prompt, and primary sections in order", async ({ page }, testInfo) => {
    await page.goto("/");

    await expect(page).toHaveTitle(/XUUnity MCP|Unity MCP/i);
    await expect(page.getByRole("heading", { name: "XUUnity Light" })).toBeVisible();
    await expect(page.getByText("LLM-ready Unity MCP for AI agents.")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Set up Unity MCP from one prompt" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "The useful parts, without the noise." })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Small local bridge, clear setup plan, Unity evidence." })).toBeVisible();

    const sectionOrder = await page.locator("main > section").evaluateAll((sections) =>
      sections.slice(0, 4).map((section) => section.id || section.className)
    );
    expect(sectionOrder).toEqual([
      "one-prompt",
      "panel section prompt-band",
      "features",
      "how-it-works"
    ]);

    await attachPageScreenshots(page, testInfo, `homepage-${testInfo.project.name}`);
  });

  test("copies the one-prompt setup text with the README URL", async ({ context, page }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.goto("/");

    await page.getByRole("button", { name: "Copy prompt" }).click();
    await expect(page.getByRole("button", { name: "Copied" })).toBeVisible();

    const clipboardText = await page.evaluate(() => navigator.clipboard.readText());
    expect(clipboardText).toContain("Set up XUUnity MCP from");
    expect(clipboardText).toContain(`the repository README (${README_URL})`);
    expect(clipboardText).toContain("/path/to/UnityProject");
    expect(clipboardText).toContain("run EditMode tests");
  });

  test("has no horizontal overflow in the tested viewport", async ({ page }) => {
    await page.goto("/");

    const pageWidths = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth
    }));
    expect(pageWidths.scrollWidth).toBeLessThanOrEqual(pageWidths.clientWidth);

    const overflowingElements = await collectVisibleOverflow(page);
    expect(overflowingElements).toEqual([]);
  });

  test("has no critical or serious automated accessibility violations", async ({ page }) => {
    await page.goto("/");

    const scan = await new AxeBuilder({ page }).analyze();
    const highImpactViolations = scan.violations.filter((violation) =>
      violation.impact === "critical" || violation.impact === "serious"
    );

    expect(highImpactViolations).toEqual([]);
  });

  test("opens foldout details without layout breakage", async ({ page }) => {
    await page.goto("/");

    for (const label of ["Validation details", "Exact install commands for agents", "Decision frame", "FAQ"]) {
      await page.getByText(label, { exact: true }).click();
    }

    await expect(page.getByText("Setup proof")).toBeVisible();
    await expect(page.getByText("Git UPM package")).toBeVisible();
    await expect(page.getByText("Choose XUUnity MCP when")).toBeVisible();
    await expect(page.getByText("Does one-prompt setup skip approval?")).toBeVisible();

    const overflowingElements = await collectVisibleOverflow(page);
    expect(overflowingElements).toEqual([]);
  });
});

test.describe("important docs routes", () => {
  for (const route of [
    "/install.html",
    "/comparison.html",
    "/clients/",
    "/articles/",
    "/articles/introducing-xuunity-mcp.html",
    "/articles/xuunity-mcp-vs-unity-mcp.html",
    "/articles/run-unity-compile-checks-and-tests-through-mcp.html"
  ]) {
    test(`loads ${route}`, async ({ page }) => {
      const response = await page.goto(route);
      expect(response?.ok()).toBeTruthy();
      await expect(page.locator("h1, h2").first()).toBeVisible();
    });
  }
});
