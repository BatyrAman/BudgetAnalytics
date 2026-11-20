import { expect, test } from "@playwright/test";

import fs from "node:fs";

import { STORAGE_STATE, USER_FILE } from "./global-setup";
import { PASSWORD, loginUser, registerUser } from "./helpers";

// Registration is limited to 10 per hour per IP, so only the sign-up flow itself
// registers; the other tests reuse the user created in global-setup.

test.describe("authentication and session", () => {
  test("register, sign out, sign in again", async ({ page }) => {
    const email = await registerUser(page, "auth");

    await page.getByRole("button", { name: "Меню пользователя" }).click();
    await page.getByRole("menuitem", { name: "Выйти" }).click();
    await expect(page).toHaveURL(/\/login/);

    // After logout the app pages are protected again.
    await page.goto("/transactions");
    await expect(page).toHaveURL(/\/login\?next=%2Ftransactions/);

    // The guard added ?next=/transactions; signing in returns the user there.
    await loginUser(page, email, undefined, { navigate: false });
    await expect(page).toHaveURL(/\/transactions$/);
  });

  test("wrong password shows a Russian message from the machine error code", async ({ page }) => {
    const email = fs.readFileSync(USER_FILE, "utf8").trim();
    await loginUser(page, email, `${PASSWORD}-wrong`);
    await expect(
      page.getByRole("alert").filter({ hasText: "Неверный e-mail или пароль." }),
    ).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });

  test("tokens are httpOnly cookies and never exposed to JavaScript", async ({ browser }) => {
    const context = await browser.newContext({ storageState: STORAGE_STATE });
    const page = await context.newPage();
    await page.goto("/dashboard");
    await page.waitForURL(/\/dashboard$/);
    const cookies = await page.context().cookies();
    const session = cookies.filter((cookie) => cookie.name === "ba_at" || cookie.name === "ba_rt");
    expect(session).toHaveLength(2);
    for (const cookie of session) {
      expect(cookie.httpOnly).toBe(true);
      expect(cookie.sameSite).toBe("Strict");
    }
    const visible = await page.evaluate(() => document.cookie);
    expect(visible).not.toContain("ba_at");
    expect(visible).not.toContain("ba_rt");
    await context.close();
  });

  test("the API proxy refuses token endpoints and mutations without the CSRF header", async ({
    browser,
    request,
  }) => {
    const context = await browser.newContext({ storageState: STORAGE_STATE });
    const page = await context.newPage();
    await page.goto("/dashboard");
    const tokenEndpoint = await request.post("/api/v1/auth/login", {
      data: { email: "x@example.com", password: "x" },
      headers: { "X-Requested-With": "fetch" },
    });
    expect(tokenEndpoint.status()).toBe(404);
    // An encoded slash must not smuggle the token endpoint past the block list.
    const encoded = await request.post("/api/v1/auth%2Flogin", {
      data: { email: "x@example.com", password: "x" },
      headers: { "X-Requested-With": "fetch" },
    });
    expect(encoded.status()).toBe(404);

    const noCsrfHeader = await page.evaluate(async () => {
      const response = await fetch("/api/v1/categories", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "CSRF" }),
      });
      return { status: response.status, body: await response.json() };
    });
    expect(noCsrfHeader.status).toBe(403);
    expect(noCsrfHeader.body.code).toBe("csrf_rejected");
    await context.close();
  });

  test("password recovery is marked as requiring backend", async ({ page }) => {
    await page.goto("/forgot-password");
    await expect(
      page.getByText("Восстановление пароля пока недоступно — требует backend"),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Отправить ссылку" })).toBeDisabled();
  });
});
