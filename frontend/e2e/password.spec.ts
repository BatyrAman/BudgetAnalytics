import { expect, test } from "@playwright/test";

import { PASSWORD, loginUser, registerUser } from "./helpers";

const NEW_PASSWORD = "E2e-N3w-Passw0rd!";

test("change password ends every session and only the new password works", async ({ page }) => {
  // Own user: changing the shared user's password would break the other specs.
  const email = await registerUser(page, "pwchange");
  await page.goto("/settings?section=security");

  await page.getByLabel("Текущий пароль", { exact: true }).fill("wrong-current-1");
  await page.getByLabel("Новый пароль", { exact: true }).fill(NEW_PASSWORD);
  await page.getByLabel("Повторите новый пароль").fill(NEW_PASSWORD);
  await page.getByRole("button", { name: "Изменить пароль" }).click();
  await expect(page.getByText("Неверный текущий пароль").first()).toBeVisible();

  await page.getByLabel("Текущий пароль", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Изменить пароль" }).click();
  await expect(page).toHaveURL(/\/login/, { timeout: 15_000 });

  // The old session is gone: protected pages redirect to login.
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login/);

  await loginUser(page, email, PASSWORD);
  await expect(
    page.getByRole("alert").filter({ hasText: "Неверный e-mail или пароль." }),
  ).toBeVisible();
  await loginUser(page, email, NEW_PASSWORD);
  await expect(page).toHaveURL(/\/dashboard$/);
});
