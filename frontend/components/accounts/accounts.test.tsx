import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SWRConfig } from "swr";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { Account, Overview, User } from "@/lib/types";
import { AccountDetailContent } from "./account-detail-screen";
import { AccountsContent } from "./accounts-screen";

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getMe: vi.fn(),
  listAccounts: vi.fn(),
  getAccount: vi.fn(),
  listBanks: vi.fn(),
  getOverview: vi.fn(),
  createAccount: vi.fn(),
  updateAccount: vi.fn(),
  deleteAccount: vi.fn(),
  listTransactions: vi.fn(),
  listCategories: vi.fn(),
}));
vi.mock("@/components/app-shell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  StatePreviewSwitcher: () => null,
}));

const user: User = {
  id: 1,
  full_name: "Test",
  email: "t@example.com",
  is_active: true,
  default_currency_code: "KZT",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};
const account = (
  id: number,
  currency: string,
  balance: string,
  patch: Partial<Account> = {},
): Account => ({
  id,
  name: `Счёт ${id}`,
  account_type: "card",
  currency_code: currency,
  bank_id: null,
  last4: null,
  is_archived: false,
  opening_balance: "0.00",
  opening_balance_at: "2026-01-01T00:00:00Z",
  balance,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  ...patch,
});
const overview = (currency: string, balance: string | null): Overview => ({
  generated_at: "2026-11-19T10:00:00Z",
  timezone: "Asia/Almaty",
  currency_code: currency,
  month: "2026-11",
  current_balance: balance,
  accounts: [],
  monthly_income: "0.00",
  monthly_expenses: "0.00",
  monthly_net_cash_flow: "0.00",
  budgets: [],
  indicators: {
    savings_rate: null,
    expense_to_income_percent: null,
    expense_change_percent: null,
    income_change_percent: null,
    average_monthly_expenses_3m: null,
    emergency_fund_months: null,
    budgets_exceeded: 0,
    budgets_total: 0,
    deposits_principal: "0.00",
    deposits_expected_interest: "0.00",
  },
});

const withSWR = (ui: React.ReactNode) =>
  render(<SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>{ui}</SWRConfig>);

beforeEach(() => {
  vi.mocked(api.getMe).mockResolvedValue(user);
  vi.mocked(api.listBanks).mockResolvedValue([{ id: 3, name: "Kaspi", logo: null }]);
  vi.mocked(api.listCategories).mockResolvedValue([]);
  // Deliberately inconsistent with the account balances (100 + 200 ≠ 999.99):
  // the UI must show the backend total, never a client-side sum.
  vi.mocked(api.getOverview).mockImplementation(async (currency) =>
    currency === "KZT" ? overview("KZT", "999.99") : overview(currency ?? "KZT", "1.23"),
  );
  vi.mocked(api.listAccounts).mockResolvedValue([
    account(1, "KZT", "100.00"),
    account(2, "KZT", "200.00"),
    account(3, "EUR", "50.00"),
  ]);
});

describe("AC-1 Список счетов", () => {
  it("groups by currency and takes group totals only from the overview", async () => {
    withSWR(<AccountsContent />);
    expect(await screen.findByTestId("group-total-KZT")).toHaveTextContent("999,99 ₸");
    expect(await screen.findByTestId("group-total-EUR")).toHaveTextContent("1,23 €");
    expect(screen.queryByText("300,00 ₸")).not.toBeInTheDocument();

    const groups = screen.getAllByRole("region");
    expect(groups.map((g) => g.getAttribute("aria-label"))).toEqual(["Счета в KZT", "Счета в EUR"]);
    expect(within(groups[0]).getAllByRole("link")).toHaveLength(2);
    // One overview request per currency the user actually has; nothing hardcoded.
    expect(
      vi
        .mocked(api.getOverview)
        .mock.calls.map(([c]) => c)
        .sort(),
    ).toEqual(["EUR", "KZT"]);
  });

  it("requests archived accounts when the toggle is on", async () => {
    withSWR(<AccountsContent />);
    await screen.findByTestId("group-total-KZT");
    await userEvent.click(screen.getByLabelText("Показать архивные"));
    await waitFor(() => expect(api.listAccounts).toHaveBeenCalledWith(true));
  });

  it("creates an account with a string amount and an ISO datetime, then revalidates", async () => {
    vi.mocked(api.createAccount).mockResolvedValue(account(9, "USD", "-1500.50"));
    withSWR(<AccountsContent />);
    await screen.findByTestId("group-total-KZT");
    const callsBefore = vi.mocked(api.listAccounts).mock.calls.length;

    await userEvent.click(screen.getByRole("button", { name: "Добавить счёт" }));
    const dialog = screen.getByRole("dialog", { name: "Новый счёт" });
    await userEvent.type(within(dialog).getByLabelText(/Название/), "Кредитка");
    await userEvent.selectOptions(within(dialog).getByLabelText(/Тип/), "credit_card");
    await userEvent.selectOptions(within(dialog).getByLabelText(/Валюта/), "USD");
    await userEvent.selectOptions(within(dialog).getByLabelText(/Банк/), "3");
    await userEvent.type(within(dialog).getByLabelText(/Последние 4 цифры/), "1234");
    const balance = within(dialog).getByLabelText(/^Начальный остаток/);
    await userEvent.clear(balance);
    await userEvent.type(balance, "-1 500,50");
    const date = within(dialog).getByLabelText(/Дата начального остатка/);
    await userEvent.clear(date);
    await userEvent.type(date, "2026-11-01");
    await userEvent.click(within(dialog).getByRole("button", { name: "Создать счёт" }));

    await waitFor(() =>
      expect(api.createAccount).toHaveBeenCalledWith({
        name: "Кредитка",
        account_type: "credit_card",
        currency: "USD",
        bank_id: 3,
        last4: "1234",
        opening_balance: "-1500.50",
        opening_balance_at: "2026-11-01T00:00:00+05:00",
      }),
    );
    const sent = vi.mocked(api.createAccount).mock.calls[0][0];
    expect(typeof sent.opening_balance).toBe("string");
    await waitFor(() =>
      expect(vi.mocked(api.listAccounts).mock.calls.length).toBeGreaterThan(callsBefore),
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("names fields by their label only; hints are descriptions", async () => {
    withSWR(<AccountsContent />);
    await screen.findByTestId("group-total-KZT");
    await userEvent.click(screen.getByRole("button", { name: "Добавить счёт" }));
    const dialog = screen.getByRole("dialog");
    expect(
      within(dialog).getByRole("textbox", { name: "Последние 4 цифры" }),
    ).toHaveAccessibleDescription("Никогда не вводите полный номер карты, CVV или PIN");
    expect(
      within(dialog).getByRole("textbox", { name: "Начальный остаток" }),
    ).toHaveAccessibleDescription("Для кредитной карты укажите долг со знаком минус");
    expect(within(dialog).getByRole("combobox", { name: "Валюта" })).toHaveAccessibleDescription(
      "Валюту нельзя изменить после создания",
    );
  });

  it("rejects last4 that is not exactly 4 digits without calling the API", async () => {
    withSWR(<AccountsContent />);
    await screen.findByTestId("group-total-KZT");
    await userEvent.click(screen.getByRole("button", { name: "Добавить счёт" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(/Название/), "Карта");
    await userEvent.type(within(dialog).getByLabelText(/Последние 4 цифры/), "123");
    await userEvent.click(within(dialog).getByRole("button", { name: "Создать счёт" }));
    expect(await within(dialog).findByText("Укажите ровно 4 цифры.")).toBeInTheDocument();
    expect(api.createAccount).not.toHaveBeenCalled();
  });

  it("maps business and field errors from the API to form fields", async () => {
    vi.mocked(api.createAccount)
      .mockRejectedValueOnce(new ApiError({ status: 409, code: "account_name_taken" }))
      .mockRejectedValueOnce(
        new ApiError({
          status: 422,
          code: "validation_error",
          fieldErrors: [{ field: "opening_balance", message: "Слишком большое число." }],
        }),
      );
    withSWR(<AccountsContent />);
    await screen.findByTestId("group-total-KZT");
    await userEvent.click(screen.getByRole("button", { name: "Добавить счёт" }));
    const dialog = screen.getByRole("dialog");
    const name = within(dialog).getByLabelText(/Название/);
    await userEvent.type(name, "Дубль");
    await userEvent.click(within(dialog).getByRole("button", { name: "Создать счёт" }));
    expect(await within(dialog).findByText("Счёт с таким названием уже есть.")).toBeInTheDocument();
    expect(name).toHaveAttribute("aria-invalid", "true");

    await userEvent.click(within(dialog).getByRole("button", { name: "Создать счёт" }));
    expect(await within(dialog).findByText("Слишком большое число.")).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/^Начальный остаток/)).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });
});

describe("AC-2 Детали счёта", () => {
  beforeEach(() => {
    vi.mocked(api.getAccount).mockResolvedValue(
      account(5, "KZT", "-1500.00", { name: "Kaspi Gold" }),
    );
    vi.mocked(api.listTransactions).mockResolvedValue({
      items: [],
      total: 0,
      limit: 10,
      offset: 0,
    });
  });

  it("loads the account and its operations filtered by account_id", async () => {
    withSWR(<AccountDetailContent id={5} />);
    expect(await screen.findByRole("heading", { name: "Kaspi Gold" })).toBeInTheDocument();
    expect(screen.getByText("−1 500,00 ₸")).toHaveClass("text-negative");
    expect(api.getAccount).toHaveBeenCalledWith(5);
    await waitFor(() =>
      expect(api.listTransactions).toHaveBeenCalledWith({ account_id: 5, limit: 10, offset: 0 }),
    );
    expect(screen.getByText("Требует backend")).toBeInTheDocument();
  });

  it("offers archiving when delete returns 409 account_has_transactions", async () => {
    vi.mocked(api.deleteAccount).mockRejectedValue(
      new ApiError({ status: 409, code: "account_has_transactions" }),
    );
    vi.mocked(api.updateAccount).mockResolvedValue(
      account(5, "KZT", "-1500.00", { name: "Kaspi Gold", is_archived: true }),
    );
    withSWR(<AccountDetailContent id={5} />);
    await screen.findByRole("heading", { name: "Kaspi Gold" });
    // No client-side pre-check: the backend decides.
    expect(api.listTransactions).not.toHaveBeenCalledWith(expect.objectContaining({ limit: 1 }));

    await userEvent.click(screen.getByRole("button", { name: "Действия со счётом" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Удалить" }));
    const dialog = screen.getByRole("alertdialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Удалить" }));

    expect(api.deleteAccount).toHaveBeenCalledWith(5);
    expect(await within(dialog).findByText(/На счёте есть операции/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Архивировать" }));
    await waitFor(() => expect(api.updateAccount).toHaveBeenCalledWith(5, { is_archived: true }));
    expect(await screen.findByText("Счёт перемещён в архив")).toBeInTheDocument();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("shows «Счёт не найден» for a 404", async () => {
    vi.mocked(api.getAccount).mockRejectedValue(
      new ApiError({ status: 404, code: "account_not_found" }),
    );
    withSWR(<AccountDetailContent id={77} />);
    expect(await screen.findByText("Счёт не найден")).toBeInTheDocument();
    expect(screen.getByText("Счёт не найден или недоступен.")).toBeInTheDocument();
  });
});
