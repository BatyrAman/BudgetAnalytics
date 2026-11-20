import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SWRConfig } from "swr";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { Account, CategoryBreakdown, Monthly, Overview, User } from "@/lib/types";
import { DashboardContent } from "./dashboard-content";
import { currentYearMonth } from "./period";

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getMe: vi.fn(),
  getOverview: vi.fn(),
  getMonthly: vi.fn(),
  getCategoryBreakdown: vi.fn(),
  listTransactions: vi.fn(),
  listCategories: vi.fn(),
  listAccounts: vi.fn(),
}));
// Recharts needs layout APIs that jsdom lacks; chart month selection is tested separately.
vi.mock("@/components/dashboard-charts", () => ({
  CashflowChart: ({ data }: { data: Monthly }) => (
    <div data-testid="cashflow">{`${data.currency_code}:${data.months.length}`}</div>
  ),
  ExpenseDonut: ({ data }: { data: CategoryBreakdown }) => (
    <div data-testid="donut">{data.currency_code}</div>
  ),
}));
vi.mock("@/components/app-shell", () => ({ StatePreviewSwitcher: () => null }));

// Testing Library normalises NBSP in the DOM text to a plain space before matching.
const NBSP = " ";
const user: User = {
  id: 1,
  full_name: "Test",
  email: "t@example.com",
  is_active: true,
  default_currency_code: "KZT",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};
const account = (id: number, currency: string): Account => ({
  id,
  name: `Счёт ${id}`,
  account_type: "card",
  currency_code: currency,
  bank_id: null,
  last4: null,
  is_archived: false,
  opening_balance: "0.00",
  opening_balance_at: "2026-01-01T00:00:00Z",
  balance: "0.00",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
});
const overview = (currency: string, patch: Partial<Overview["indicators"]> = {}): Overview => ({
  generated_at: "2026-11-19T10:00:00Z",
  timezone: "Asia/Almaty",
  currency_code: currency,
  month: "2026-11",
  current_balance: currency === "KZT" ? "1250000.50" : "1500.00",
  accounts: [],
  monthly_income: currency === "KZT" ? "450000.00" : "2000.00",
  monthly_expenses: "180000.00",
  monthly_net_cash_flow: "270000.00",
  budgets: [
    {
      budget_id: 7,
      title: "Продукты",
      limit: "100000.00",
      spent: "85000.00",
      utilization_percent: "85.00",
      is_exceeded: false,
    },
  ],
  indicators: {
    savings_rate: "60.00",
    expense_to_income_percent: "40.00",
    expense_change_percent: "-5.00",
    income_change_percent: "10.00",
    average_monthly_expenses_3m: "175000.00",
    emergency_fund_months: "7.14",
    budgets_exceeded: 0,
    budgets_total: 1,
    deposits_principal: "0.00",
    deposits_expected_interest: "0.00",
    ...patch,
  },
});
const monthly = (currency: string): Monthly => ({
  year: 2026,
  timezone: "Asia/Almaty",
  currency_code: currency,
  months: Array.from({ length: 12 }, (_, i) => ({
    month: `2026-${String(i + 1).padStart(2, "0")}`,
    income: "0.00",
    net_expenses: "0.00",
    net_cash_flow: "0.00",
    savings_rate: null,
    transaction_count: 0,
  })),
  total: {
    month: "2026",
    income: "0.00",
    net_expenses: "0.00",
    net_cash_flow: "0.00",
    savings_rate: null,
    transaction_count: 0,
  },
});
const breakdown = (currency: string): CategoryBreakdown => ({
  period: { date_from: "2026-11-01", date_to: "2026-11-30", timezone: "Asia/Almaty" },
  currency_code: currency,
  kind: "expense",
  total: "100.00",
  items: [
    {
      category_id: 1,
      name: "Еда",
      amount: "100.00",
      transaction_count: 1,
      share_percent: "100.00",
    },
  ],
});

function renderDashboard() {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <DashboardContent />
    </SWRConfig>,
  );
}

beforeEach(() => {
  vi.mocked(api.getMe).mockResolvedValue(user);
  vi.mocked(api.getOverview).mockImplementation(async (currency) => overview(currency ?? "KZT"));
  vi.mocked(api.getMonthly).mockImplementation(async (_year, currency) =>
    monthly(currency ?? "KZT"),
  );
  vi.mocked(api.getCategoryBreakdown).mockImplementation(async (_kind, filters) =>
    breakdown(filters?.currency ?? "KZT"),
  );
  vi.mocked(api.listTransactions).mockResolvedValue({
    items: [
      {
        id: 1,
        amount: "12500.00",
        currency_code: "KZT",
        description: "Магазин",
        transaction_type: "expense",
        transaction_date: "2026-11-18T10:00:00Z",
        category_id: 1,
        bank_id: null,
        account_id: 1,
        created_at: "2026-11-18T10:00:00Z",
        updated_at: "2026-11-18T10:00:00Z",
      },
    ],
    total: 1,
    limit: 5,
    offset: 0,
  });
  vi.mocked(api.listCategories).mockResolvedValue([
    { id: 1, name: "Еда", color: "#000", icon: "x", kind: "expense", is_system: true },
  ]);
  vi.mocked(api.listAccounts).mockResolvedValue([account(1, "KZT"), account(2, "USD")]);
});

describe("D-1 Обзор — currency before and after the profile loads", () => {
  /** The backend answers without `currency` in the user's default currency (here EUR). */
  function serverDefaultsTo(code: string) {
    vi.mocked(api.getOverview).mockImplementation(async (currency) => overview(currency ?? code));
    vi.mocked(api.getMonthly).mockImplementation(async (_year, currency) =>
      monthly(currency ?? code),
    );
  }

  it("profile loading: requests the overview once, without a guessed currency", async () => {
    vi.mocked(api.getMe).mockReturnValue(new Promise(() => {})); // never resolves
    serverDefaultsTo("EUR");
    renderDashboard();
    await waitFor(() => expect(api.getOverview).toHaveBeenCalledTimes(1));
    expect(api.getOverview).toHaveBeenCalledWith(undefined);
    expect(api.getOverview).not.toHaveBeenCalledWith("KZT");
  });

  it("profile success: no second request; the shown currency comes from the response", async () => {
    vi.mocked(api.getMe).mockResolvedValue({ ...user, default_currency_code: "EUR" });
    serverDefaultsTo("EUR");
    renderDashboard();
    await waitFor(() => expect(screen.getByTestId("cashflow")).toHaveTextContent("EUR:12"));
    await waitFor(() => expect(api.getMe).toHaveBeenCalled());
    // Give SWR a chance to issue a duplicate if the key changed after the profile loaded.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(api.getOverview).toHaveBeenCalledTimes(1);
    expect(api.getMonthly).toHaveBeenCalledTimes(1);
    expect(api.getCategoryBreakdown).toHaveBeenCalledTimes(1);
  });

  it("profile failure: the overview still loads in the server's default currency", async () => {
    vi.mocked(api.getMe).mockRejectedValue(new Error("profile unavailable"));
    serverDefaultsTo("KZT");
    renderDashboard();
    expect(await screen.findByText(`1${NBSP}250${NBSP}000,50${NBSP}₸`)).toBeInTheDocument();
    expect(api.getOverview).toHaveBeenCalledTimes(1);
  });

  it("an explicit pick sends that currency (and only then)", async () => {
    serverDefaultsTo("KZT");
    renderDashboard();
    const select = await screen.findByRole("combobox", { name: "Валюта отчёта" });
    expect(api.getOverview).not.toHaveBeenCalledWith("USD");
    await userEvent.selectOptions(select, "USD");
    await waitFor(() => expect(api.getOverview).toHaveBeenLastCalledWith("USD"));
  });
});

describe("D-1 Обзор", () => {
  it("renders overview numbers formatted from API strings and requests the current year", async () => {
    renderDashboard();
    expect(await screen.findByText(`1${NBSP}250${NBSP}000,50${NBSP}₸`)).toBeInTheDocument();
    expect(screen.getByText(`450${NBSP}000${NBSP}₸`)).toBeInTheDocument();
    expect(screen.getByText(`60${NBSP}%`)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Ноябрь 2026" })).toBeInTheDocument();
    // Budgets come from overview.budgets only.
    expect(screen.getByText("Продукты")).toBeInTheDocument();
    // Recent operations: the desktop table and the phone list (CSS shows one of them).
    expect(
      within(screen.getByRole("table")).getByText(`−12${NBSP}500,00${NBSP}₸`),
    ).toBeInTheDocument();
    const phoneList = screen.getByRole("list", { name: "Последние операции" });
    expect(within(phoneList).getByText("Магазин")).toBeInTheDocument();
    expect(within(phoneList).getByText(`−12${NBSP}500,00${NBSP}₸`)).toBeInTheDocument();
    expect(within(phoneList).getByText(/^Еда · /)).toBeInTheDocument();
    expect(screen.getByTestId("cashflow")).toHaveTextContent("KZT:12");

    const { year } = currentYearMonth(api.currentTimezone());
    // No currency until the user picks one: the backend answers in the user's default (G-4).
    expect(api.getMonthly).toHaveBeenCalledWith(year, undefined);
    expect(api.listTransactions).toHaveBeenCalledWith({ limit: 5 });
    expect(api.getCategoryBreakdown).toHaveBeenCalledWith("expense", {});
  });

  it("refetches all currency-dependent data when the currency is switched", async () => {
    renderDashboard();
    const select = await screen.findByRole("combobox", { name: "Валюта отчёта" });
    expect(
      within(select)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["KZT", "USD"]);
    await userEvent.selectOptions(select, "USD");

    expect(await screen.findByText(`1${NBSP}500${NBSP}$`)).toBeInTheDocument();
    expect(api.getOverview).toHaveBeenLastCalledWith("USD");
    expect(api.getMonthly).toHaveBeenLastCalledWith(expect.any(Number), "USD");
    expect(api.getCategoryBreakdown).toHaveBeenLastCalledWith("expense", { currency: "USD" });
    await waitFor(() => expect(screen.getByTestId("cashflow")).toHaveTextContent("USD:12"));
  });

  it("shows «—» with an explanation for null indicators", async () => {
    vi.mocked(api.getOverview).mockResolvedValue(
      overview("KZT", {
        savings_rate: null,
        emergency_fund_months: null,
        average_monthly_expenses_3m: null,
        expense_to_income_percent: null,
      }),
    );
    renderDashboard();
    expect(await screen.findByText("Не считается без доходов за месяц")).toBeInTheDocument();
    expect(screen.getByTitle("Норма сбережений не считается без доходов")).toBeInTheDocument();
    const hint = screen.getByTitle(/Недостаточно данных о расходах/);
    expect(hint).toHaveTextContent("—");
    expect(screen.queryByText(/0\s*мес\./)).not.toBeInTheDocument();
  });

  it("shows a Russian error message by machine code", async () => {
    vi.mocked(api.getOverview).mockRejectedValue(
      new ApiError({ status: 404, code: "unknown_timezone" }),
    );
    renderDashboard();
    expect(
      await screen.findByText("Неизвестный часовой пояс. Выберите другой в настройках."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Повторить/ })).toBeInTheDocument();
  });

  it("shows onboarding when the user has no accounts and no transactions", async () => {
    vi.mocked(api.listAccounts).mockResolvedValue([]);
    vi.mocked(api.listTransactions).mockResolvedValue({ items: [], total: 0, limit: 5, offset: 0 });
    renderDashboard();
    expect(await screen.findByRole("link", { name: /Добавьте счёт/ })).toHaveAttribute(
      "href",
      "/accounts",
    );
    expect(screen.getByRole("link", { name: /Добавьте операцию/ })).toHaveAttribute(
      "href",
      "/transactions?new=1",
    );
    expect(screen.getByRole("link", { name: /Импортируйте выписку/ })).toHaveAttribute(
      "href",
      "/transactions/import",
    );
  });
});
