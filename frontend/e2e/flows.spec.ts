/**
 * Main product flows against the real backend (no API mocks). One user is
 * created in global-setup and these tests run in order on its data. Expected
 * financial values are computed by hand in the comments, never by the app.
 */
import { expect, test, type Page } from "@playwright/test";

import { STORAGE_STATE } from "./global-setup";
import { expectNoHorizontalOverflow } from "./helpers";

const NBSP = " ";
const money = (text: string) => text.replace(/ /g, NBSP);

test.use({ storageState: STORAGE_STATE });
test.describe.configure({ mode: "serial" });

async function selectByLabel(page: Page, label: RegExp | string, option: string) {
  await page.getByLabel(label).selectOption({ label: option });
}

test("dashboard: a new user sees onboarding, not fake numbers", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Ваши финансы — под контролем" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Добавьте счёт/ })).toBeVisible();
  await expectNoHorizontalOverflow(page);
});

test("accounts: create a card with an opening balance", async ({ page }) => {
  await page.goto("/accounts");
  await page.getByRole("button", { name: "Добавить счёт" }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel(/^Название/).fill("Kaspi Gold");
  await selectByLabel(page, /^Тип/, "Карта");
  await selectByLabel(page, /^Банк/, "Kaspi Bank");
  await dialog.getByLabel(/^Последние 4 цифры/).fill("4417");
  await dialog.getByLabel(/^Начальный остаток/).fill("100000");
  await dialog.getByRole("button", { name: /Сохранить|Создать/ }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(page.getByText("Kaspi Gold").filter({ visible: true }).first()).toBeVisible();
  await expect(
    page.getByText(money("100 000,00 ₸")).filter({ visible: true }).first(),
  ).toBeVisible();
});

test("categories: tabs and a custom category", async ({ page }) => {
  await page.goto("/categories");
  await expect(page.getByRole("tab", { name: "Расходы" })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("button", { name: "+ Создать категорию" }).click();
  await page
    .getByRole("dialog")
    .getByLabel(/^Название/)
    .fill("E2E Хобби");
  await page.getByRole("dialog").getByRole("button", { name: "Сохранить" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(page.getByText("E2E Хобби").filter({ visible: true }).first()).toBeVisible();
  await page.getByRole("tab", { name: "Доходы" }).click();
  await expect(page.getByText("Зарплата").filter({ visible: true }).first()).toBeVisible();
});

async function addOperation(
  page: Page,
  {
    type,
    amount,
    category,
    description,
  }: { type: string; amount: string; category: string; description: string },
) {
  await page.goto("/transactions?new=1");
  const dialog = page.getByRole("dialog", { name: "Добавить операцию" });
  await dialog.getByRole("button", { name: type, exact: true }).click();
  await dialog.getByLabel(/^Сумма/).fill(amount);
  await dialog.getByLabel(/^Категория/).selectOption({ label: category });
  await dialog.getByLabel(/^Счёт/).selectOption({ label: "Kaspi Gold · KZT" });
  await dialog.getByLabel(/^Описание/).fill(description);
  await dialog
    .getByRole("button", { name: /Сохранить|Добавить/ })
    .last()
    .click();
  await expect(dialog).toBeHidden();
}

test("operations: create an expense and an income; the list shows signed amounts", async ({
  page,
}) => {
  await addOperation(page, {
    type: "Расход",
    amount: "12500,50",
    category: "Продукты",
    description: "Magnum E2E",
  });
  await addOperation(page, {
    type: "Доход",
    amount: "650000",
    category: "Зарплата",
    description: "Зарплата E2E",
  });
  await page.goto("/transactions");
  await expect(page.getByText("Magnum E2E").filter({ visible: true }).first()).toBeVisible();
  await expect(
    page.getByText(money("−12 500,50 ₸")).filter({ visible: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText(money("+650 000,00 ₸")).filter({ visible: true }).first(),
  ).toBeVisible();
  await expect(page.getByText("Сначала новые").filter({ visible: true }).first()).toBeVisible();
});

test("accounts: the backend balance reflects the operations", async ({ page }) => {
  // 100 000,00 + 650 000,00 − 12 500,50 = 737 499,50
  await page.goto("/accounts");
  await expect(
    page.getByText(money("737 499,50 ₸")).filter({ visible: true }).first(),
  ).toBeVisible();
});

test("dashboard: monthly figures and savings rate from the backend", async ({ page }) => {
  await page.goto("/dashboard");
  // Income 650 000; expenses 12 500,50; savings rate (650 000 − 12 500,50) / 650 000 = 98,077 % → 98,08 %
  await expect(page.getByText(money("650 000 ₸")).filter({ visible: true }).first()).toBeVisible();
  await expect(
    page.getByText(money("12 500,50 ₸")).filter({ visible: true }).first(),
  ).toBeVisible();
  await expect(page.getByText(`98,08${NBSP}%`).filter({ visible: true }).first()).toBeVisible();
});

test("budgets: create a budget and see utilization from /budgets/utilization", async ({ page }) => {
  await page.goto("/budgets");
  await page.getByRole("button", { name: "Создать бюджет" }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel(/^Название/).fill("Продукты E2E");
  await dialog.getByLabel(/^Месячный лимит/).fill("15000");
  await dialog.getByLabel(/^Категория/).selectOption({ label: "Продукты" });
  await dialog.getByRole("button", { name: "Сохранить бюджет" }).click();
  await expect(dialog).toBeHidden();
  // 12 500,50 / 15 000 = 83,337 % → 83,34 %, ≥ 80 % → warning (D-7)
  await expect(page.getByText(`83,34${NBSP}%`).filter({ visible: true }).first()).toBeVisible();
  await expect(page.getByText("Близко к лимиту").filter({ visible: true }).first()).toBeVisible();
});

test("goals: progress, remaining and monthly saving come from the backend", async ({ page }) => {
  await page.goto("/goals");
  await page.getByRole("button", { name: "Новая цель" }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel(/^Название/).fill("Ноутбук");
  await dialog.getByLabel(/^Целевая сумма/).fill("600000");
  await dialog.getByLabel(/^Уже накоплено/).fill("150000");
  await dialog.getByRole("button", { name: "Сохранить цель" }).click();
  await expect(dialog).toBeHidden();
  // 150 000 / 600 000 = 25 %; remaining 450 000
  await expect(page.getByText(`25${NBSP}%`).filter({ visible: true }).first()).toBeVisible();
  await expect(
    page.getByText(money("450 000,00 ₸")).filter({ visible: true }).first(),
  ).toBeVisible();
});

test("deposits: calculator matches the control example (monthly capitalization, ACT/365)", async ({
  page,
}) => {
  await page.goto("/deposits/calculator");
  await page.getByLabel(/^Сумма/).fill("1000000");
  await page.getByLabel(/^Номинальная ставка/).fill("16");
  await page.getByLabel(/^Капитализация/).selectOption({ label: "Ежемесячно" });
  await page.getByLabel(/^Дата начала/).fill("2026-01-01");
  await page.getByLabel(/^Срок в месяцах \*/).fill("12");
  await page.getByRole("button", { name: "Рассчитать" }).click();
  // 1 000 000 · ((1 + 0,16/12)^12 − 1) = 172 270,80; EAR 17,2271 %
  await expect(
    page.getByText(money("172 270,80 ₸")).filter({ visible: true }).first(),
  ).toBeVisible();
  await expect(page.getByText(`17,2271${NBSP}%`).filter({ visible: true }).first()).toBeVisible();
});

test("deposits: save a deposit and see it in the list", async ({ page }) => {
  await page.goto("/deposits");
  await page.getByRole("button", { name: "Добавить депозит" }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel(/^Банк/).selectOption({ label: "Halyk Bank" });
  await dialog.getByLabel(/^Сумма/).fill("1000000");
  await dialog.getByLabel(/^Номинальная ставка/).fill("14");
  await dialog.getByLabel(/^Капитализация/).selectOption({ label: "Ежегодно" });
  await dialog.getByLabel(/^Дата начала/).fill("2026-01-01");
  await dialog.getByLabel(/^Дата окончания/).fill("2028-01-01");
  await dialog.getByRole("button", { name: "Сохранить депозит" }).click();
  // Annual capitalization, 2 years: 1 000 000 · (1,14² − 1) = 299 600,00
  await expect(page.getByText("Halyk Bank").filter({ visible: true }).first()).toBeVisible();
  await expect(
    page.getByText(money("299 600,00 ₸")).filter({ visible: true }).first(),
  ).toBeVisible();
});

test("AI advisor: a question gets a rules-based answer with its source", async ({ page }) => {
  await page.goto("/advisor");
  await page.getByLabel("Ваш вопрос").fill("Ок");
  await page.getByRole("button", { name: "Отправить вопрос" }).click();
  await expect(
    page.getByText("Вопрос должен быть от 3 до 500 символов").filter({ visible: true }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Куда уходит больше всего денег?" }).click();
  // The E2E backend runs with AI_PROVIDER=none, so the answer must be labelled as rules.
  await expect(page.getByText("Ответ по правилам").filter({ visible: true }).first()).toBeVisible({
    timeout: 20_000,
  });
  await expect(
    page.getByText("AI отключён, ответ подготовлен по правилам").filter({ visible: true }).first(),
  ).toBeVisible();
  await expect(
    page
      .getByText(/История не сохраняется/)
      .filter({ visible: true })
      .first(),
  ).toBeVisible();
});

test("financial report: sections, disclaimers, no persistence", async ({ page }) => {
  await page.goto("/advisor/report");
  await expect(
    page
      .getByText("Отчёт не сохраняется; повторное формирование расходует лимит")
      .filter({ visible: true })
      .first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Сформировать отчёт" }).click();
  await expect(page.getByText("Отчёт по правилам").filter({ visible: true }).first()).toBeVisible({
    timeout: 20_000,
  });
  for (const section of ["Наблюдения", "Рекомендации", "Риски", "Допущения"]) {
    await expect(page.locator("details > summary", { hasText: section }).first()).toBeVisible();
  }
});

test("notifications: marked as requiring backend, no working bulk actions", async ({ page }) => {
  await page.goto("/notifications");
  await expect(
    page.getByText(
      "Уведомления пока не поддерживаются backend — экран показывает планируемый дизайн",
    ),
  ).toBeVisible();
  await expect(
    page.getByText("Уведомлений пока нет").filter({ visible: true }).first(),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Отметить всё прочитанным" })).toBeDisabled();
});

test("settings: theme switch applies Graphite + Teal and persists", async ({ page }) => {
  await page.goto("/settings?section=appearance");
  const themes = page.getByRole("group", { name: "Тема" });
  await themes.getByRole("button", { name: "Тёмная" }).click();
  await expect(themes.getByRole("button", { name: "Тёмная" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.reload();
  await expect(page.locator("html")).toHaveClass(/dark/);
  const background = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(background).toBe("rgb(13, 17, 23)"); // #0D1117
  await page.getByRole("group", { name: "Тема" }).getByRole("button", { name: "Светлая" }).click();
  await expect(page.locator("html")).not.toHaveClass(/dark/);
});

test("session: an expired access token is refreshed on the server transparently", async ({
  page,
  context,
}) => {
  await page.goto("/goals");
  await expect(page.getByText("Ноутбук").filter({ visible: true }).first()).toBeVisible();
  const cookies = await context.cookies();
  await context.clearCookies();
  await context.addCookies(cookies.filter((cookie) => cookie.name !== "ba_at"));
  await page.reload();
  await expect(page.getByText("Ноутбук").filter({ visible: true }).first()).toBeVisible();
  const after = await context.cookies();
  expect(after.some((cookie) => cookie.name === "ba_at")).toBe(true);
});

test("session: without any session cookie the app redirects to login", async ({
  page,
  context,
}) => {
  await context.clearCookies();
  await page.goto("/budgets");
  await expect(page).toHaveURL(/\/login\?next=%2Fbudgets/);
});
