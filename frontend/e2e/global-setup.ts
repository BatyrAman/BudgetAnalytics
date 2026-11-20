import fs from "node:fs";
import path from "node:path";

import { chromium, type FullConfig } from "@playwright/test";

import { PASSWORD, uniqueEmail } from "./helpers";

export const STORAGE_STATE = path.join(__dirname, ".auth", "user.json");
export const USER_FILE = path.join(__dirname, ".auth", "user-email.txt");

/**
 * Registers ONE user through the real UI for all feature specs and stores its
 * session cookies. The backend allows 10 registrations per hour per IP, so specs
 * must not register a user each — only auth and password-change specs do.
 */
export default async function globalSetup(config: FullConfig): Promise<void> {
  const baseURL = config.projects[0].use.baseURL as string;
  fs.mkdirSync(path.dirname(STORAGE_STATE), { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ baseURL });
  const email = uniqueEmail("main");
  await page.goto("/register");
  await page.getByLabel("Имя").fill("Айгерим Тестова");
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Пароль", { exact: true }).fill(PASSWORD);
  await page.getByLabel("Подтвердите пароль").fill(PASSWORD);
  await page.getByRole("button", { name: "Создать аккаунт" }).click();
  await page.waitForURL(/\/dashboard$/);
  await page.context().storageState({ path: STORAGE_STATE });
  fs.writeFileSync(USER_FILE, email);
  await browser.close();
}
