import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SWRConfig } from "swr";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { Category } from "@/lib/types";

import { CategoriesScreen } from "./categories-screen";

vi.mock("@/components/app-shell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  listCategories: vi.fn(),
  createCategory: vi.fn(),
  updateCategory: vi.fn(),
  deleteCategory: vi.fn(),
  listTransactions: vi.fn(),
  listBudgets: vi.fn(),
}));

const mocked = vi.mocked(api);

function renderWithSWR(ui: React.ReactElement) {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>{ui}</SWRConfig>,
  );
}

const system: Category = {
  id: 1,
  name: "Продукты",
  color: "#22C55E",
  icon: "shopping-cart",
  kind: "expense",
  is_system: true,
};
const own: Category = {
  id: 7,
  name: "Хобби",
  color: "#4776C7",
  icon: "film",
  kind: "expense",
  is_system: false,
};
const anyKind: Category = {
  id: 8,
  name: "Разное",
  color: "#607D8B",
  icon: "dots",
  kind: "any",
  is_system: false,
};
const salary: Category = {
  id: 2,
  name: "Зарплата",
  color: "#16A34A",
  icon: "briefcase",
  kind: "income",
  is_system: true,
};

beforeEach(() => {
  mocked.listCategories.mockImplementation(async (kind) =>
    kind === "income" ? [salary, anyKind] : [system, own, anyKind],
  );
});

describe("CategoriesScreen (C-1)", () => {
  it("lists expense tab, shows «Любой тип» and keeps system categories read-only", async () => {
    renderWithSWR(<CategoriesScreen />);
    const table = await screen.findByRole("table");
    expect(mocked.listCategories).toHaveBeenCalledWith("expense");
    const systemRow = within(table).getByText("Продукты").closest("tr") as HTMLElement;
    expect(within(systemRow).getByText("Только чтение")).toBeInTheDocument();
    expect(within(systemRow).queryByRole("button")).not.toBeInTheDocument();
    const anyRow = within(table).getByText("Разное").closest("tr") as HTMLElement;
    expect(within(anyRow).getByText("Любой тип")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "Доходы" }));
    expect(await within(screen.getByRole("table")).findByText("Зарплата")).toBeInTheDocument();
    expect(mocked.listCategories).toHaveBeenCalledWith("income");
    expect(within(screen.getByRole("table")).getByText("Разное")).toBeInTheDocument();
  });

  it("explains 409 category_in_use without any client-side pre-check", async () => {
    mocked.deleteCategory.mockRejectedValue(new ApiError({ status: 409, code: "category_in_use" }));
    renderWithSWR(<CategoriesScreen />);
    const table = await screen.findByRole("table");
    await userEvent.click(within(table).getByRole("button", { name: "Удалить «Хобби»" }));
    const confirm = screen.getByRole("alertdialog");
    await userEvent.click(within(confirm).getByRole("button", { name: "Удалить" }));

    const dialog = await screen.findByRole("alertdialog", { name: "Удалить нельзя" });
    expect(dialog).toHaveTextContent("используется в операциях или бюджетах");
    expect(mocked.deleteCategory).toHaveBeenCalledWith(7);
    expect(mocked.listTransactions).not.toHaveBeenCalled();
    expect(mocked.listBudgets).not.toHaveBeenCalled();

    await userEvent.click(within(dialog).getByRole("button", { name: "Понятно" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("deletes an unused category and revalidates the list", async () => {
    mocked.deleteCategory.mockResolvedValue(undefined);
    renderWithSWR(<CategoriesScreen />);
    const table = await screen.findByRole("table");
    const callsBefore = mocked.listCategories.mock.calls.length;
    await userEvent.click(within(table).getByRole("button", { name: "Удалить «Хобби»" }));
    await userEvent.click(
      within(screen.getByRole("alertdialog")).getByRole("button", { name: "Удалить" }),
    );
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(mocked.deleteCategory).toHaveBeenCalledWith(7);
    expect(mocked.listCategories.mock.calls.length).toBeGreaterThan(callsBefore);
  });

  it("creates a category with palette colour and icon; maps category_exists to the name", async () => {
    mocked.createCategory.mockRejectedValueOnce(
      new ApiError({ status: 409, code: "category_exists" }),
    );
    mocked.createCategory.mockResolvedValueOnce({ ...own, id: 9, name: "Спорт" });
    renderWithSWR(<CategoriesScreen />);
    await screen.findByRole("table");
    await userEvent.click(screen.getByRole("button", { name: "+ Создать категорию" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/Название/), "Продукты");
    await userEvent.click(within(dialog).getByRole("radio", { name: "Цвет #C65353" }));
    await userEvent.click(within(dialog).getByRole("radio", { name: "Кино" }));
    await userEvent.selectOptions(within(dialog).getByLabelText("Тип"), "any");
    await userEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));

    expect(
      await within(dialog).findByText("Категория с таким названием уже есть."),
    ).toBeInTheDocument();
    expect(mocked.createCategory).toHaveBeenCalledWith({
      name: "Продукты",
      kind: "any",
      color: "#C65353",
      icon: "film",
    });

    const name = within(dialog).getByLabelText(/Название/);
    await userEvent.clear(name);
    await userEvent.type(name, "Спорт");
    await userEvent.click(within(dialog).getByRole("button", { name: "Сохранить" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("rejects too short names locally", async () => {
    renderWithSWR(<CategoriesScreen />);
    await screen.findByRole("table");
    await userEvent.click(screen.getByRole("button", { name: "+ Создать категорию" }));
    await userEvent.type(screen.getByLabelText(/Название/), "А");
    await userEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    expect(await screen.findByText(/от 2 до 100 символов/)).toBeInTheDocument();
    expect(mocked.createCategory).not.toHaveBeenCalled();
  });

  it("shows the backend 409 when the kind change conflicts with operations", async () => {
    mocked.updateCategory.mockRejectedValue(
      new ApiError({ status: 409, code: "category_kind_conflict" }),
    );
    renderWithSWR(<CategoriesScreen />);
    const table = await screen.findByRole("table");
    await userEvent.click(within(table).getByRole("button", { name: "Изменить «Хобби»" }));
    await userEvent.selectOptions(screen.getByLabelText("Тип"), "income");
    await userEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    expect(
      await screen.findByText("Нельзя сменить тип: есть операции, несовместимые с новым типом."),
    ).toBeInTheDocument();
    expect(mocked.updateCategory).toHaveBeenCalledWith(
      7,
      expect.objectContaining({ kind: "income" }),
    );
    expect(mocked.listTransactions).not.toHaveBeenCalled();
  });

  it("shows an error state with a Russian message", async () => {
    mocked.listCategories.mockRejectedValue(
      new ApiError({ status: 503, code: "backend_unavailable" }),
    );
    renderWithSWR(<CategoriesScreen />);
    expect(await screen.findByText("Сервер недоступен. Попробуйте позже.")).toBeInTheDocument();
  });
});
