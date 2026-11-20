/**
 * Responsive and theme QA on real data (the global-setup user after flows.spec).
 * For every screen × width × theme: no horizontal page scroll, no visible element
 * sticking out of the viewport, and the navigation pattern for that width.
 * Set QA_SHOTS_DIR to also save full-page screenshots for manual review.
 */
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { STORAGE_STATE } from "./global-setup";
import { expectNoHorizontalOverflow } from "./helpers";

test.use({ storageState: STORAGE_STATE });

const WIDTHS = [375, 390, 768, 1024, 1280, 1440] as const;
const THEMES = ["light", "dark"] as const;
const SCREENS = [
  "/dashboard",
  "/transactions",
  "/accounts",
  "/categories",
  "/budgets",
  "/goals",
  "/deposits",
  "/deposits/calculator",
  "/analytics",
  "/advisor",
  "/advisor/report",
  "/notifications",
  "/settings",
] as const;
const SHOTS = process.env.QA_SHOTS_DIR;

/** Visible elements whose box crosses the right edge, ignoring intentional scrollers. */
async function elementsOutsideViewport(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const width = document.documentElement.clientWidth;
    const clipped = (element: Element) => {
      for (let node = element.parentElement; node; node = node.parentElement) {
        const overflowX = getComputedStyle(node).overflowX;
        if (overflowX !== "visible") return true;
      }
      return false;
    };
    const found: string[] = [];
    for (const element of Array.from(document.body.querySelectorAll("*"))) {
      const rect = element.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) continue;
      if (rect.right <= width + 1) continue;
      const style = getComputedStyle(element);
      if (style.visibility === "hidden" || style.position === "fixed") continue;
      if (clipped(element)) continue;
      const name =
        element.className && typeof element.className === "string"
          ? `.${element.className.split(" ")[0]}`
          : "";
      found.push(`${element.tagName.toLowerCase()}${name} right=${Math.round(rect.right)}`);
      if (found.length >= 5) break;
    }
    return found;
  });
}

for (const theme of THEMES) {
  for (const width of WIDTHS) {
    test(`${theme} ${width}px: screens fit and use the right navigation`, async ({ page }) => {
      await page.addInitScript((value) => window.localStorage.setItem("theme", value), theme);
      await page.setViewportSize({ width, height: width < 768 ? 812 : 900 });
      for (const screen of SCREENS) {
        await page.goto(screen);
        await expect(page).toHaveURL(new RegExp(`${screen}$`));
        await expect(page.locator("main").first()).toBeVisible();
        await page.waitForLoadState("networkidle");
        if (theme === "dark") await expect(page.locator("html")).toHaveClass(/dark/);

        await expectNoHorizontalOverflow(page);
        expect(await elementsOutsideViewport(page), `${screen} at ${width}px`).toEqual([]);

        const bottomNav = page.locator("nav.bottom-nav");
        const sidebar = page.locator(".sidebar");
        if (width <= 700) {
          await expect(bottomNav).toBeVisible();
          await expect(sidebar).toBeHidden();
        } else {
          await expect(bottomNav).toBeHidden();
          await expect(sidebar).toBeVisible();
        }

        if (screen === "/dashboard") {
          // Phones swap the recent-operations table for a list; one of them must show data.
          const recent =
            width <= 700
              ? page.getByRole("list", { name: "Последние операции" })
              : page.locator(".recent-card table");
          await expect(recent).toBeVisible();
        }

        if (SHOTS) {
          const file = `${theme}-${width}-${screen.slice(1).replace(/\//g, "_")}.png`;
          await page.screenshot({ path: path.join(SHOTS, file), fullPage: true });
        }
      }
    });
  }
}

test("mobile 375px: the operation form dialog fits and its fields stay reachable", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await page.goto("/transactions");
  await page
    .getByRole("button", { name: /Добавить|Новая операция/ })
    .filter({ visible: true })
    .first()
    .click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  const box = await dialog.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(375 + 1);
  await expectNoHorizontalOverflow(page);
  const submit = dialog.getByRole("button", { name: "Добавить операцию" });
  await submit.scrollIntoViewIfNeeded();
  await expect(submit).toBeInViewport();
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, "light-375-transaction-dialog.png") });
});
