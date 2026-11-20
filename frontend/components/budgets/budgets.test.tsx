import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SWRConfig } from "swr";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { Budget, BudgetUtilization, Category, User } from "@/lib/types";

import { BudgetDetailScreen } from "./budget-detail-screen";
import { BudgetForm } from "./budget-form";
import { BudgetsScreen } from "./budgets-screen";
import { currentMonth, monthBounds, shiftMonth } from "./month";

vi.mock("@/components/app-shell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  getMe: vi.fn(),
  listBudgets: vi.fn(),
  listBudgetUtilization: vi.fn(),
  getBudgetUtilization: vi.fn(),
  getBudget: vi.fn(),
  listTransactions: vi.fn(),
  listAccounts: vi.fn(),
  listBanks: vi.fn(),
  listCategories: vi.fn(),
  createBudget: vi.fn(),
  updateBudget: vi.fn(),
}));

const mocked = vi.mocked(api);
// Testing Library normalises the NBSP used by formatMoney to plain spaces.

function renderWithSWR(ui: React.ReactElement) {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>{ui}</SWRConfig>,
  );
}

const me: User = {
  id: 1,
  full_name: "Тест",
  email: "test@example.com",
  is_active: true,
  default_currency_code: "USD",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const categories: Category[] = [
  {
    id: 10,
    name: "Продукты",
    color: "#22C55E",
    icon: "shopping-cart",
    kind: "expense",
    is_system: true,
  },
  { id: 11, name: "Разное", color: "#4776C7", icon: "tag", kind: "any", is_system: false },
];

// Raw API objects still carry the DEPRECATED manual fields; they must never be shown.
const deprecated = { spent: "777.77", remaining: "-999.99", progress: 0.42, is_exceeded: true };
const rawBudgets = [
  {
    id: 1,
    title: "Еда",
    monthly_limit: "10000.00",
    currency_code: "KZT",
    category_id: 10,
    ...deprecated,
  },
  {
    id: 2,
    title: "Разное",
    monthly_limit: "5000.00",
    currency_code: "KZT",
    category_id: 11,
    ...deprecated,
  },
  {
    id: 3,
    title: "Все траты",
    monthly_limit: "10000.00",
    currency_code: "KZT",
    category_id: null,
    ...deprecated,
  },
];
const budgets: Budget[] = rawBudgets;

function usage(budget_id: number, patch: Partial<BudgetUtilization>): BudgetUtilization {
  return {
    budget_id,
    month: "2026-11",
    currency_code: "KZT",
    limit: "10000.00",
    spent: "0.00",
    remaining: "10000.00",
    utilization_percent: "0.00",
    is_exceeded: false,
    ...patch,
  };
}

const usages: BudgetUtilization[] = [
  usage(1, { spent: "3000.00", remaining: "7000.00", utilization_percent: "30.00" }),
  usage(2, {
    limit: "5000.00",
    spent: "4250.00",
    remaining: "750.00",
    utilization_percent: "85.00",
  }),
  usage(3, {
    spent: "12000.00",
    remaining: "-2000.00",
    utilization_percent: "120.00",
    is_exceeded: true,
  }),
];

beforeEach(() => {
  mocked.getMe.mockResolvedValue(me);
  mocked.listCategories.mockResolvedValue(categories);
  mocked.listBudgets.mockResolvedValue({ items: budgets, total: 3, limit: 20, offset: 0 });
  mocked.listBudgetUtilization.mockResolvedValue(usages);
});

describe("BudgetsScreen (B-1)", () => {
  it("loads usage of all budgets with ONE utilization call and ignores deprecated fields", async () => {
    renderWithSWR(<BudgetsScreen />);

    expect(await screen.findByText("3 000,00 ₸")).toBeInTheDocument();
    expect(mocked.listBudgetUtilization).toHaveBeenCalledTimes(1);
    expect(mocked.listBudgetUtilization).toHaveBeenCalledWith(currentMonth("Asia/Almaty"));
    expect(mocked.getBudgetUtilization).not.toHaveBeenCalled();
    expect(mocked.listBudgets).toHaveBeenCalledWith({ limit: 20, offset: 0 });

    const page = document.body.textContent ?? "";
    expect(page).not.toContain("777");
    expect(page).not.toContain("999");
    // Summary is a count from the utilization list.
    const summary = screen.getByLabelText("Сводка по бюджетам");
    expect(summary).toHaveTextContent("1 из 3");
  });

  it("shows category names and «Все расходы» for budgets without a category", async () => {
    renderWithSWR(<BudgetsScreen />);
    const card = (await screen.findByRole("heading", { name: "Все траты" })).closest("a");
    expect(card).not.toBeNull();
    expect(within(card as HTMLElement).getByText("Все расходы")).toBeInTheDocument();
    expect(await screen.findByText("Продукты")).toBeInTheDocument();
  });

  it("applies normal / warning / exceeded tones and caps the bar at 100 %", async () => {
    renderWithSWR(<BudgetsScreen />);
    await screen.findByText("3 000,00 ₸");
    const fills = screen.getAllByTestId("budget-progress-fill");
    expect(fills.map((fill) => fill.className)).toEqual([
      expect.stringContaining("is-normal"),
      expect.stringContaining("is-warning"),
      expect.stringContaining("is-over"),
    ]);
    expect(fills[2]).toHaveStyle({ width: "100%" });
    expect(screen.getByText("120,00 %")).toBeInTheDocument();
    // Overspend comes from the API `remaining`, shown without the minus sign.
    expect(screen.getByText("Превышен на 2 000,00 ₸")).toBeInTheDocument();
    expect(screen.getByText("Близко к лимиту")).toBeInTheDocument();
    expect(screen.getByText("В пределах лимита")).toBeInTheDocument();
  });

  it("shows the empty state", async () => {
    mocked.listBudgets.mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
    mocked.listBudgetUtilization.mockResolvedValue([]);
    renderWithSWR(<BudgetsScreen />);
    expect(await screen.findByText("Бюджетов пока нет")).toBeInTheDocument();
  });

  it("shows a Russian error by machine code and retries", async () => {
    mocked.listBudgets.mockRejectedValueOnce(new ApiError({ status: 422, code: "invalid_month" }));
    renderWithSWR(<BudgetsScreen />);
    expect(await screen.findByText("Некорректный месяц.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Повторить/ }));
    expect(await screen.findByText("3 000,00 ₸")).toBeInTheDocument();
  });
});

describe("BudgetForm (B-3)", () => {
  it("sends the limit as a string, the profile currency and null category for «Все расходы»", async () => {
    const saved: Budget = {
      id: 9,
      title: "Новый",
      monthly_limit: "12500.50",
      currency_code: "USD",
      category_id: null,
    };
    mocked.createBudget.mockResolvedValue(saved);
    const onSaved = vi.fn();
    const onClose = vi.fn();
    renderWithSWR(<BudgetForm onClose={onClose} onSaved={onSaved} />);

    const currency = screen.getByLabelText("Валюта");
    await waitFor(() => expect(currency).toHaveValue("USD"));
    expect(screen.getByLabelText("Категория")).toHaveValue("");
    expect(await screen.findByRole("option", { name: "Разное · Любой тип" })).toBeInTheDocument();
    expect(screen.queryByLabelText(/Потрачено/)).not.toBeInTheDocument();

    await userEvent.type(screen.getByLabelText(/Название/), "Новый");
    await userEvent.type(screen.getByLabelText(/Месячный лимит/), "12 500,50");
    await userEvent.click(screen.getByRole("button", { name: "Сохранить бюджет" }));

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(mocked.createBudget).toHaveBeenCalledWith({
      title: "Новый",
      monthly_limit: "12500.50",
      currency: "USD",
      category_id: null,
    });
    expect(onSaved).toHaveBeenCalledWith(saved);
    expect(mocked.listCategories).toHaveBeenCalledWith("expense");
  });

  it("validates the limit locally without calling the API", async () => {
    renderWithSWR(<BudgetForm onClose={vi.fn()} onSaved={vi.fn()} />);
    await userEvent.type(screen.getByLabelText(/Название/), "Еда");
    await userEvent.type(screen.getByLabelText(/Месячный лимит/), "0");
    await userEvent.click(screen.getByRole("button", { name: "Сохранить бюджет" }));
    expect(await screen.findByText(/Лимит должен быть числом больше нуля/)).toBeInTheDocument();
    expect(mocked.createBudget).not.toHaveBeenCalled();
  });

  it("shows the budget_income_category message at the category field", async () => {
    mocked.createBudget.mockRejectedValue(
      new ApiError({ status: 400, code: "budget_income_category" }),
    );
    const onClose = vi.fn();
    renderWithSWR(<BudgetForm onClose={onClose} onSaved={vi.fn()} />);
    await screen.findByRole("option", { name: "Продукты" });
    await userEvent.type(screen.getByLabelText(/Название/), "Еда");
    await userEvent.type(screen.getByLabelText(/Месячный лимит/), "1000");
    await userEvent.selectOptions(screen.getByLabelText("Категория"), "10");
    await userEvent.click(screen.getByRole("button", { name: "Сохранить бюджет" }));

    expect(
      await screen.findByText("Бюджет ограничивает расходы — выберите расходную категорию."),
    ).toBeInTheDocument();
    expect(mocked.createBudget).toHaveBeenCalledWith(expect.objectContaining({ category_id: 10 }));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("maps validation field errors to inputs", async () => {
    mocked.createBudget.mockRejectedValue(
      new ApiError({
        status: 422,
        code: "validation_error",
        fieldErrors: [{ field: "title", message: "Слишком длинное значение." }],
      }),
    );
    renderWithSWR(<BudgetForm onClose={vi.fn()} onSaved={vi.fn()} />);
    await userEvent.type(screen.getByLabelText(/Название/), "Еда");
    await userEvent.type(screen.getByLabelText(/Месячный лимит/), "100");
    await userEvent.click(screen.getByRole("button", { name: "Сохранить бюджет" }));
    expect(await screen.findByText("Слишком длинное значение.")).toBeInTheDocument();
    expect(screen.getByLabelText(/Название/)).toHaveAttribute("aria-invalid", "true");
  });
});

describe("BudgetDetailScreen (B-2)", () => {
  beforeEach(() => {
    mocked.getBudget.mockResolvedValue(budgets[0]);
    mocked.getBudgetUtilization.mockImplementation(async (id, month) =>
      usage(id, {
        month: month ?? "",
        spent: "3000.00",
        remaining: "7000.00",
        utilization_percent: "30.00",
      }),
    );
    mocked.listTransactions.mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
    mocked.listAccounts.mockResolvedValue([]);
    mocked.listBanks.mockResolvedValue([]);
  });

  it("defaults to the current month in the user's zone and loads that month's operations", async () => {
    const month = currentMonth("Asia/Almaty");
    renderWithSWR(<BudgetDetailScreen id={1} />);

    expect(await screen.findByText("7 000,00 ₸")).toBeInTheDocument();
    expect(mocked.getBudgetUtilization).toHaveBeenCalledWith(1, month);
    const { start, end } = monthBounds(month, "Asia/Almaty");
    await waitFor(() =>
      expect(mocked.listTransactions).toHaveBeenCalledWith(
        expect.objectContaining({
          category_id: 10,
          transaction_type: "expense",
          currency: "KZT",
          start_date: start,
          end_date: end,
        }),
      ),
    );
    // Deprecated manual fields of the budget object are not shown.
    expect(document.body.textContent ?? "").not.toContain("777");

    await userEvent.click(screen.getByRole("button", { name: "Предыдущий месяц" }));
    await waitFor(() =>
      expect(mocked.getBudgetUtilization).toHaveBeenCalledWith(1, shiftMonth(month, -1)),
    );
    expect(screen.getByRole("button", { name: "Следующий месяц" })).toBeEnabled();
  });

  it("shows budget_not_found as a Russian error", async () => {
    mocked.getBudget.mockRejectedValue(new ApiError({ status: 404, code: "budget_not_found" }));
    renderWithSWR(<BudgetDetailScreen id={42} />);
    expect(await screen.findByText("Бюджет не найден.")).toBeInTheDocument();
  });
});
