import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "@/lib/api/client";
import type { TransactionDetail } from "@/lib/types";

import { TransactionsScreen } from "./transactions-screen";
import {
  account,
  apiError,
  banks,
  categories,
  navigation,
  page,
  renderWithSWR,
  transaction,
} from "./test-utils";

vi.mock("next/navigation", async () => (await import("./test-utils")).navigationMock());
vi.mock("@/components/app-shell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getMe: vi.fn(),
  listCategories: vi.fn(),
  listAccounts: vi.fn(),
  listBanks: vi.fn(),
  listTransactions: vi.fn(),
  getTransaction: vi.fn(),
  deleteTransaction: vi.fn(),
  createTransaction: vi.fn(),
}));

const api = vi.mocked(client);

beforeEach(() => {
  navigation.setUrl("");
  api.getMe.mockResolvedValue({
    id: 1,
    full_name: "Тест",
    email: "t@example.com",
    is_active: true,
    default_currency_code: "KZT",
    created_at: "",
    updated_at: "",
  });
  api.listCategories.mockResolvedValue(categories);
  api.listAccounts.mockResolvedValue([account()]);
  api.listBanks.mockResolvedValue(banks);
});

describe("TransactionsScreen (T-1)", () => {
  it("calls the API with the filters from the URL and joins reference names", async () => {
    navigation.setUrl(
      "category_id=1&start_date=2026-11-01T00%3A00%3A00%2B05%3A00&end_date=2026-11-30T23%3A59%3A59%2B05%3A00",
    );
    api.listTransactions.mockResolvedValue(page([transaction({ bank_id: 1 })]));

    renderWithSWR(<TransactionsScreen />);

    await waitFor(() =>
      expect(api.listTransactions).toHaveBeenCalledWith({
        category_id: 1,
        start_date: "2026-11-01T00:00:00+05:00",
        end_date: "2026-11-30T23:59:59+05:00",
        limit: 20,
        offset: 0,
      }),
    );
    const table = (await screen.findAllByRole("table"))[0];
    await within(table).findByText("Тестовый банк");
    expect(within(table).getAllByText("Продукты").length).toBeGreaterThan(0);
    expect(within(table).getByText("Карта")).toBeInTheDocument();
    expect(screen.getAllByText("Сначала новые").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Поиск по описанию")).toBeInTheDocument();
  });

  it("paginates with limit/offset and keeps the page in the URL", async () => {
    const user = userEvent.setup();
    api.listTransactions.mockResolvedValue(page([transaction()], 45));

    renderWithSWR(<TransactionsScreen />);
    await screen.findByText("Показано 1–1 из 45");

    await user.click(screen.getByRole("button", { name: "Следующая страница" }));
    await waitFor(() =>
      expect(api.listTransactions).toHaveBeenLastCalledWith({ limit: 20, offset: 20 }),
    );
    expect(navigation.current().get("offset")).toBe("20");

    await user.selectOptions(screen.getByLabelText(/^На странице/), "50");
    await waitFor(() =>
      expect(api.listTransactions).toHaveBeenLastCalledWith({ limit: 50, offset: 0 }),
    );
    expect(navigation.current().toString()).toBe("limit=50");
  });

  it("applies a period preset with local-day ISO bounds and resets the offset", async () => {
    const user = userEvent.setup();
    navigation.setUrl("offset=40");
    api.listTransactions.mockResolvedValue(page([transaction()], 60));

    renderWithSWR(<TransactionsScreen />);
    await screen.findAllByRole("table");
    await user.click(screen.getAllByRole("button", { name: "Прошлый месяц" })[0]);

    await waitFor(() => {
      const last = api.listTransactions.mock.lastCall?.[0];
      expect(last?.offset).toBe(0);
      expect(last?.start_date).toMatch(/^\d{4}-\d{2}-01T00:00:00\+05:00$/);
      expect(last?.end_date).toMatch(/^\d{4}-\d{2}-\d{2}T23:59:59\.999999\+05:00$/);
    });
  });

  it("shows the Russian error message and retries", async () => {
    const user = userEvent.setup();
    api.listTransactions.mockRejectedValueOnce(apiError(422, "invalid_amount_range"));
    api.listTransactions.mockResolvedValue(page([]));

    renderWithSWR(<TransactionsScreen />);
    expect(
      await screen.findByText("Минимальная сумма не может быть больше максимальной."),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Повторить/ }));
    expect(await screen.findByText("Пока нет операций")).toBeInTheDocument();
  });

  it("opens the create dialog for ?new=1", async () => {
    navigation.setUrl("new=1");
    api.listTransactions.mockResolvedValue(page([]));
    renderWithSWR(<TransactionsScreen />);
    expect(await screen.findByRole("dialog", { name: "Добавить операцию" })).toBeInTheDocument();
  });

  it("deletes from the details drawer after confirmation and revalidates the list", async () => {
    const user = userEvent.setup();
    const item = transaction();
    const detail: TransactionDetail = { ...item, category_name: "Продукты", bank_name: "—" };
    api.listTransactions.mockResolvedValue(page([item]));
    api.getTransaction.mockResolvedValue(detail);
    api.deleteTransaction.mockResolvedValue(undefined);

    renderWithSWR(<TransactionsScreen />);
    const table = (await screen.findAllByRole("table"))[0];
    await user.click(within(table).getByText("Покупка"));

    const drawer = await screen.findByRole("dialog", { name: "Детали операции" });
    expect(api.getTransaction).toHaveBeenCalledWith(100);
    await user.click(within(drawer).getByRole("button", { name: "Удалить" }));
    const confirm = screen.getByRole("alertdialog", { name: "Удалить операцию?" });
    expect(api.deleteTransaction).not.toHaveBeenCalled();

    const callsBefore = api.listTransactions.mock.calls.length;
    await user.click(within(confirm).getByRole("button", { name: "Удалить" }));

    await waitFor(() => expect(api.deleteTransaction).toHaveBeenCalledWith(100));
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Детали операции" })).not.toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(api.listTransactions.mock.calls.length).toBeGreaterThan(callsBefore),
    );
  });

  it("opens details directly for /transactions/[id] and shows not found", async () => {
    api.listTransactions.mockResolvedValue(page([]));
    api.getTransaction.mockRejectedValue(apiError(404, "transaction_not_found"));
    renderWithSWR(<TransactionsScreen initialId={77} />);
    expect(await screen.findByText("Операция не найдена")).toBeInTheDocument();
    expect(api.getTransaction).toHaveBeenCalledWith(77);
  });
});
