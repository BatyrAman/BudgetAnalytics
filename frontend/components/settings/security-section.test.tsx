import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { changePassword, logoutAll } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { SecuritySection } from "./security-section";

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  changePassword: vi.fn(),
  logoutAll: vi.fn(),
}));

// Session-ending actions reload the page so no data of this session stays in memory.
const navigation = vi.hoisted(() => ({ navigateWithFullReload: vi.fn() }));
vi.mock("@/lib/navigation", () => navigation);

async function fillPassword(current: string, next: string, confirm: string) {
  if (current)
    fireEvent.change(screen.getByLabelText("Текущий пароль"), { target: { value: current } });
  if (next) fireEvent.change(screen.getByLabelText("Новый пароль"), { target: { value: next } });
  if (confirm)
    fireEvent.change(screen.getByLabelText("Повторите новый пароль"), {
      target: { value: confirm },
    });
  await userEvent.click(screen.getByRole("button", { name: "Изменить пароль" }));
}

// Generous timeout: jsdom renders are slow on a loaded CI/dev machine.
describe("SecuritySection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(changePassword).mockResolvedValue({ message: "ok" });
    vi.mocked(logoutAll).mockResolvedValue(undefined);
  });

  it("validates length and confirmation before calling the API", async () => {
    render(<SecuritySection />);
    await fillPassword("", "short", "other");
    expect(screen.getByText("Введите текущий пароль")).toBeInTheDocument();
    expect(screen.getByText("Пароль должен быть от 8 до 128 символов")).toBeInTheDocument();
    expect(screen.getByText("Пароли не совпадают")).toBeInTheDocument();
    expect(changePassword).not.toHaveBeenCalled();
  });

  it("maps wrong_password to the current-password field", async () => {
    vi.mocked(changePassword).mockRejectedValue(
      new ApiError({ status: 400, code: "wrong_password" }),
    );
    render(<SecuritySection />);
    await fillPassword("old-secret", "new-secret-1", "new-secret-1");
    expect(await screen.findByText("Неверный текущий пароль")).toBeInTheDocument();
    expect(screen.getByLabelText("Текущий пароль")).toHaveAttribute("aria-invalid", "true");
    expect(navigation.navigateWithFullReload).not.toHaveBeenCalled();
  });

  it("shows a form-level message for other errors", async () => {
    vi.mocked(changePassword).mockRejectedValue(new ApiError({ status: 0, code: "network_error" }));
    render(<SecuritySection />);
    await fillPassword("old-secret", "new-secret-1", "new-secret-1");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Нет связи с сервером. Проверьте подключение и повторите.",
    );
  });

  it("changes the password and redirects to /login", async () => {
    render(<SecuritySection />);
    await fillPassword("old-secret", "new-secret-1", "new-secret-1");
    await waitFor(() => expect(navigation.navigateWithFullReload).toHaveBeenCalledWith("/login"));
    expect(changePassword).toHaveBeenCalledWith({
      old_password: "old-secret",
      new_password: "new-secret-1",
    });
    expect(
      screen.getByText("Пароль изменён. Все сессии завершены — войдите снова"),
    ).toBeInTheDocument();
  });

  it("logs out everywhere only after confirmation", async () => {
    render(<SecuritySection />);
    await userEvent.click(screen.getByRole("button", { name: "Выйти на всех устройствах" }));
    const dialog = screen.getByRole("alertdialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Отмена" }));
    expect(logoutAll).not.toHaveBeenCalled();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Выйти на всех устройствах" }));
    await userEvent.click(
      within(screen.getByRole("alertdialog")).getByRole("button", { name: "Выйти" }),
    );
    await waitFor(() => expect(navigation.navigateWithFullReload).toHaveBeenCalledWith("/login"));
    expect(logoutAll).toHaveBeenCalledTimes(1);
  });

  it("keeps backend-only security features disabled", () => {
    render(<SecuritySection />);
    for (const title of [
      "Активные сессии",
      "Двухфакторная аутентификация",
      "Удаление аккаунта и экспорт данных",
    ]) {
      const card = screen.getByText(title).closest("article")!;
      expect(within(card).getByText("Требует backend")).toBeInTheDocument();
      expect(within(card).getByRole("button")).toBeDisabled();
    }
  });
});
