import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

/** Kiểm tra WCAG 2.1 AA bằng axe; lỗi nào cũng in rõ id + phần tử để sửa. */
export async function expectAccessible(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  const summary = results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
  expect(summary).toEqual([]);
}

/** Không có cuộn ngang (design-system §9). */
export async function expectNoHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}
