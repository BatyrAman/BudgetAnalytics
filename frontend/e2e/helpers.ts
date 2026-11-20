import { expect, type Page } from "@playwright/test";

export const PASSWORD = "E2e-Passw0rd!";

export function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
}

/** Registers a fresh user through the UI; the app signs them in and opens the dashboard. */
export async function registerUser(page: Page, prefix = "e2e"): Promise<string> {
  const email = uniqueEmail(prefix);
  await page.goto("/register");
  await page.getByLabel("Имя").fill("Тестовый Пользователь");
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Пароль", { exact: true }).fill(PASSWORD);
  await page.getByLabel("Подтвердите пароль").fill(PASSWORD);
  await page.getByRole("button", { name: "Создать аккаунт" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  return email;
}

/** Fills the login form. `navigate: false` keeps the current /login?next=… URL. */
export async function loginUser(
  page: Page,
  email: string,
  password = PASSWORD,
  { navigate = true }: { navigate?: boolean } = {},
): Promise<void> {
  if (navigate) await page.goto("/login");
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Пароль", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Войти" }).click();
}

/** Fails if the document is wider than the viewport (horizontal page scroll). */
export async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(
    scrollWidth,
    `page is ${scrollWidth}px wide in a ${clientWidth}px viewport`,
  ).toBeLessThanOrEqual(clientWidth);
}
