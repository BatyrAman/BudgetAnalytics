import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SWRConfig } from "swr";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type {
  CategoryBreakdown,
  Comparison,
  MonthSummary,
  Monthly,
  SavingsRate,
  Summary,
  User,
} from "@/lib/types";

import { AnalyticsDetails } from "./analytics-details";
import { AnalyticsOverview } from "./analytics-overview";

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getMe: vi.fn(),
  listAccounts: vi.fn(),
  listCategories: vi.fn(),
  getSummary: vi.fn(),
  getComparison: vi.fn(),
  getMonthly: vi.fn(),
  getCategoryBreakdown: vi.fn(),
  getSavingsRate: vi.fn(),
}));

const api = vi.mocked(client);

const period = { date_from: "2026-11-01", date_to: "2026-11-30", timezone: "Asia/Almaty" };
const user: User = {
  id: 1,
  full_name: "Тест",
  email: "t@example.com",
  is_active: true,
  default_currency_code: "KZT",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};
const summary: Summary = {
  period,
  currency_code: "KZT",
  income: "500000.00",
  gross_expenses: "320000.00",
  refunds: "20000.00",
  net_expenses: "300000.00",
  net_cash_flow: "200000.00",
  transfers_in: "0.00",
  transfers_out: "0.00",
  savings_rate: null,
  transaction_count: 12,
};
const month = (m: string): MonthSummary => ({
  month: m,
  income: "0.00",
  net_expenses: "0.00",
  net_cash_flow: "0.00",
  savings_rate: null,
  transaction_count: 0,
});
const comparison: Comparison = {
  timezone: "Asia/Almaty",
  currency_code: "KZT",
  current: month("2026-11"),
  previous: month("2026-10"),
  income: { current: "500000.00", previous: "0.00", change: "500000.00", change_percent: null },
  net_expenses: {
    current: "300000.00",
    previous: "250000.00",
    change: "50000.00",
    change_percent: "20.00",
  },
  net_cash_flow: {
    current: "200000.00",
    previous: "-250000.00",
    change: "450000.00",
    change_percent: "180.00",
  },
  savings_rate_change_pp: null,
};
const monthly: Monthly = {
  year: 2026,
  timezone: "Asia/Almaty",
  currency_code: "KZT",
  months: Array.from({ length: 12 }, (_, i) => month(`2026-${String(i + 1).padStart(2, "0")}`)),
  total: month("2026"),
};
const breakdown: CategoryBreakdown = {
  period,
  currency_code: "KZT",
  kind: "expense",
  total: "300000.00",
  items: [
    {
      category_id: 7,
      name: "Продукты",
      amount: "300000.00",
      transaction_count: 5,
      share_percent: "100.00",
    },
  ],
};
const savingsRate: SavingsRate = {
  period,
  currency_code: "KZT",
  income: "500000.00",
  net_expenses: "300000.00",
  savings_rate: "40.00",
  expense_to_income_percent: "60.00",
};

function renderWithSWR(ui: React.ReactElement) {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>{ui}</SWRConfig>,
  );
}

/** The income tile of the period summary (the comparison table repeats the amount). */
async function findSummaryIncome() {
  const region = await screen.findByRole("region", { name: "Итоги периода" });
  return within(region).getByText("500 000 ₸");
}

beforeEach(() => {
  // 19 Nov 2026, 10:00 in Almaty. Only Date is faked so SWR timers still run.
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-11-19T05:00:00Z"));
  api.getMe.mockResolvedValue(user);
  api.listAccounts.mockResolvedValue([]);
  api.listCategories.mockResolvedValue([]);
  api.getSummary.mockResolvedValue(summary);
  api.getComparison.mockResolvedValue(comparison);
  api.getMonthly.mockResolvedValue(monthly);
  api.getCategoryBreakdown.mockResolvedValue(breakdown);
  api.getSavingsRate.mockResolvedValue(savingsRate);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("AnalyticsOverview (AN-1)", () => {
  it("requests the current month in the user's currency, with month and currency in the right arguments", async () => {
    renderWithSWR(<AnalyticsOverview />);
    await findSummaryIncome();
    expect(api.getSummary).toHaveBeenCalledWith({
      date_from: "2026-11-01",
      date_to: "2026-11-30",
      currency: "KZT",
    });
    expect(api.getComparison).toHaveBeenCalledWith("2026-11", "KZT");
    expect(api.getMonthly).toHaveBeenCalledWith(2026, "KZT");
  });

  it("uses the default currency from the profile and switches the period preset", async () => {
    api.getMe.mockResolvedValue({ ...user, default_currency_code: "USD" });
    const user_ = userEvent.setup();
    renderWithSWR(<AnalyticsOverview />);
    await waitFor(() => expect(api.getComparison).toHaveBeenCalledWith("2026-11", "USD"));

    await user_.click(screen.getByRole("button", { name: "Прошлый месяц" }));
    await waitFor(() => expect(api.getComparison).toHaveBeenCalledWith("2026-10", "USD"));
    expect(api.getSummary).toHaveBeenCalledWith({
      date_from: "2026-10-01",
      date_to: "2026-10-31",
      currency: "USD",
    });

    await user_.click(screen.getByRole("button", { name: "3 месяца" }));
    await waitFor(() =>
      expect(api.getSummary).toHaveBeenCalledWith({
        date_from: "2026-09-01",
        date_to: "2026-11-30",
        currency: "USD",
      }),
    );
    expect(api.getComparison).toHaveBeenLastCalledWith("2026-11", "USD");
  });

  it("offers currencies of the user's accounts", async () => {
    api.listAccounts.mockResolvedValue([
      {
        id: 1,
        name: "Карта",
        account_type: "card",
        currency_code: "EUR",
        bank_id: null,
        last4: null,
        is_archived: false,
        opening_balance: "0.00",
        opening_balance_at: "2026-01-01T00:00:00Z",
        balance: "0.00",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ]);
    const user_ = userEvent.setup();
    renderWithSWR(<AnalyticsOverview />);
    const select = screen.getByLabelText("Валюта");
    await screen.findByRole("option", { name: "EUR" });
    await user_.selectOptions(select, "EUR");
    await waitFor(() => expect(api.getComparison).toHaveBeenCalledWith("2026-11", "EUR"));
    expect(api.getMonthly).toHaveBeenCalledWith(2026, "EUR");
  });

  it("shows «—» with an explanation for null values", async () => {
    renderWithSWR(<AnalyticsOverview />);
    await findSummaryIncome();
    expect(
      screen.getByTitle("Нет доходов за период — норма сбережений не рассчитывается"),
    ).toHaveTextContent("—");
    expect(
      await screen.findByTitle("В прошлом месяце было 0 — процент не считается"),
    ).toBeInTheDocument();
    // Expenses grew: lower is better, so +20 % is marked as worse.
    expect(screen.getByText(/\+20,00/)).toHaveClass("text-negative");
  });

  it("does not query with an invalid custom period", async () => {
    const user_ = userEvent.setup();
    renderWithSWR(<AnalyticsOverview />);
    await findSummaryIncome();
    await user_.click(screen.getByRole("button", { name: "Свой период" }));
    const from = screen.getByLabelText(/^С/);
    await user_.clear(from);
    await user_.type(from, "2026-12-15");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Дата начала не может быть позже даты окончания.",
    );
    expect(api.getSummary).not.toHaveBeenCalledWith(
      expect.objectContaining({ date_from: "2026-12-15" }),
    );
  });

  it("shows a Russian error from the machine code and retries", async () => {
    api.getSummary.mockRejectedValueOnce(new ApiError({ status: 422, code: "period_too_long" }));
    const user_ = userEvent.setup();
    renderWithSWR(<AnalyticsOverview />);
    expect(
      await screen.findByText("Слишком длинный период. Выберите период короче."),
    ).toBeInTheDocument();
    await user_.click(screen.getByRole("button", { name: /Повторить/ }));
    expect(await findSummaryIncome()).toBeInTheDocument();
  });

  it("shows an empty state when the period has no operations", async () => {
    api.getSummary.mockResolvedValue({ ...summary, transaction_count: 0 });
    renderWithSWR(<AnalyticsOverview />);
    expect(await screen.findByText("Нет операций за период")).toBeInTheDocument();
    expect(await screen.findByText("Нет данных для графика")).toBeInTheDocument();
  });
});

describe("AnalyticsDetails (AN-2)", () => {
  it("lists categories with links to filtered transactions and the savings rate", async () => {
    renderWithSWR(<AnalyticsDetails />);
    const link = await screen.findByRole("link", { name: /Продукты/ });
    const url = new URL(link.getAttribute("href") ?? "", "http://localhost");
    expect(url.pathname).toBe("/transactions");
    expect(url.searchParams.get("category_id")).toBe("7");
    expect(url.searchParams.get("start_date")).toBe("2026-11-01T00:00:00+05:00");
    expect(url.searchParams.get("end_date")).toBe("2026-11-30T23:59:59.999999+05:00");
    expect(api.getCategoryBreakdown).toHaveBeenCalledWith("expense", {
      date_from: "2026-11-01",
      date_to: "2026-11-30",
      currency: "KZT",
    });
    const row = link.closest("tr");
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).getByText("100,00 %")).toBeInTheDocument();
    expect(await screen.findByText("40,00 %")).toBeInTheDocument();
    expect(screen.getByText("Требует backend")).toBeInTheDocument();
  });

  it("switches to income categories", async () => {
    api.getCategoryBreakdown.mockResolvedValue({ ...breakdown, kind: "income", items: [] });
    const user_ = userEvent.setup();
    renderWithSWR(<AnalyticsDetails />);
    await user_.click(screen.getByRole("tab", { name: "Доходы" }));
    await waitFor(() =>
      expect(api.getCategoryBreakdown).toHaveBeenCalledWith("income", expect.any(Object)),
    );
    expect(await screen.findByText("Нет доходов за период")).toBeInTheDocument();
  });
});
