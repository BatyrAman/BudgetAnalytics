/**
 * Typed client for the BudgetAnalytics REST API (`/api/v1`).
 * Request/response shapes mirror the backend OpenAPI schema; money and percents
 * are decimal strings and are never converted to floats here.
 */
import { apiRequest, sessionRequest } from "./http";
import type {
  Account,
  AccountType,
  AdvisorAnswer,
  AdvisorReport,
  Bank,
  Budget,
  BudgetUtilization,
  Capitalization,
  Category,
  CategoryBreakdown,
  CategoryKind,
  Comparison,
  Deposit,
  DepositCalculation,
  ExpenseSummary,
  Goal,
  ImportBank,
  ImportRow,
  ImportSummary,
  IncomeSummary,
  Monthly,
  Overview,
  Page,
  SavingsRate,
  Summary,
  Transaction,
  TransactionDetail,
  TransactionType,
  User,
} from "@/lib/types";

import { currentTimezone } from "@/lib/timezone";

export { DEFAULT_TIMEZONE, currentTimezone } from "@/lib/timezone";

const tz = () => ({ tz: currentTimezone() });

// ---------------------------------------------------------------- session / auth

export type LoginInput = { email: string; password: string };
export type RegisterInput = { full_name: string; email: string; password: string };

export const login = (input: LoginInput) => sessionRequest<{ ok: true }>("login", input);
export const register = (input: RegisterInput) => sessionRequest<{ ok: true }>("register", input);
export const logout = () => sessionRequest<void>("logout");
export const getMe = (signal?: AbortSignal) => apiRequest<User>("/auth/me", { signal });
export const changePassword = (input: { old_password: string; new_password: string }) =>
  apiRequest<{ message: string }>("/auth/change-password", { method: "POST", json: input });
export const logoutAll = () => apiRequest<void>("/auth/logout-all", { method: "POST" });

// ---------------------------------------------------------------- reference data

export const listCategories = (kind?: Exclude<CategoryKind, "any">) =>
  apiRequest<Category[]>("/categories", { query: { kind } });
export type CategoryInput = { name: string; color?: string; icon?: string; kind?: CategoryKind };
export const createCategory = (input: CategoryInput) =>
  apiRequest<Category>("/categories", { method: "POST", json: input });
export const updateCategory = (id: number, patch: Partial<CategoryInput>) =>
  apiRequest<Category>(`/categories/${id}`, { method: "PATCH", json: patch });
export const deleteCategory = (id: number) =>
  apiRequest<void>(`/categories/${id}`, { method: "DELETE" });

export const listBanks = () => apiRequest<Bank[]>("/banks");

// ---------------------------------------------------------------- accounts

export const listAccounts = (include_archived = false) =>
  apiRequest<Account[]>("/accounts", { query: { include_archived } });
export const getAccount = (id: number) => apiRequest<Account>(`/accounts/${id}`);
export type AccountInput = {
  name: string;
  account_type: AccountType;
  currency?: string;
  bank_id?: number | null;
  last4?: string | null;
  opening_balance?: string;
  opening_balance_at?: string;
};
export type AccountPatch = Partial<Omit<AccountInput, "currency">> & { is_archived?: boolean };
export const createAccount = (input: AccountInput) =>
  apiRequest<Account>("/accounts", { method: "POST", json: input });
export const updateAccount = (id: number, patch: AccountPatch) =>
  apiRequest<Account>(`/accounts/${id}`, { method: "PATCH", json: patch });
export const deleteAccount = (id: number) =>
  apiRequest<void>(`/accounts/${id}`, { method: "DELETE" });

// ---------------------------------------------------------------- transactions

export type TransactionFilters = {
  start_date?: string;
  end_date?: string;
  category_id?: number;
  account_id?: number;
  bank_id?: number;
  transaction_type?: TransactionType;
  currency?: string;
  min_amount?: string;
  max_amount?: string;
  search?: string;
  limit?: number;
  offset?: number;
};
export const listTransactions = (filters: TransactionFilters = {}, signal?: AbortSignal) =>
  apiRequest<Page<Transaction>>("/transactions", { query: filters, signal });
export const getTransaction = (id: number) => apiRequest<TransactionDetail>(`/transactions/${id}`);
export type TransactionInput = {
  amount: string;
  transaction_type: TransactionType;
  transaction_date: string;
  category_id: number;
  description?: string | null;
  account_id?: number | null;
  bank_id?: number | null;
  currency?: string | null;
};
export const createTransaction = (input: TransactionInput) =>
  apiRequest<Transaction>("/transactions", { method: "POST", json: input });
export const updateTransaction = (id: number, patch: Partial<TransactionInput>) =>
  apiRequest<Transaction>(`/transactions/${id}`, { method: "PATCH", json: patch });
export const deleteTransaction = (id: number) =>
  apiRequest<void>(`/transactions/${id}`, { method: "DELETE" });

// ---------------------------------------------------------------- budgets (G-6)

export const listBudgets = (options: { limit?: number; offset?: number } = {}) =>
  apiRequest<Page<Budget>>("/budgets", { query: options });
export const getBudget = (id: number) => apiRequest<Budget>(`/budgets/${id}`);
/** Actual usage of one budget for a month — the only per-budget usage source. */
export const getBudgetUtilization = (id: number, month?: string) =>
  apiRequest<BudgetUtilization>(`/budgets/${id}/utilization`, { query: { month, ...tz() } });
/** Usage of all budgets for a month in one call (backend G-6 endpoint). */
export const listBudgetUtilization = (month?: string) =>
  apiRequest<BudgetUtilization[]>("/budgets/utilization", { query: { month, ...tz() } });
export type BudgetInput = {
  title: string;
  monthly_limit: string;
  currency?: string;
  category_id?: number | null;
};
export const createBudget = (input: BudgetInput) =>
  apiRequest<Budget>("/budgets", { method: "POST", json: input });
export const updateBudget = (id: number, patch: Partial<BudgetInput>) =>
  apiRequest<Budget>(`/budgets/${id}`, { method: "PATCH", json: patch });
export const deleteBudget = (id: number) =>
  apiRequest<void>(`/budgets/${id}`, { method: "DELETE" });

// ---------------------------------------------------------------- analytics

export type AnalyticsFilters = { date_from?: string; date_to?: string; currency?: string };
export const getOverview = (currency?: string) =>
  apiRequest<Overview>("/dashboard/overview", { query: { currency, ...tz() } });
export const getSummary = (filters: AnalyticsFilters = {}) =>
  apiRequest<Summary>("/analytics/summary", { query: { ...filters, ...tz() } });
export const getIncome = (filters: AnalyticsFilters = {}) =>
  apiRequest<IncomeSummary>("/analytics/income", { query: { ...filters, ...tz() } });
export const getExpenses = (filters: AnalyticsFilters = {}) =>
  apiRequest<ExpenseSummary>("/analytics/expenses", { query: { ...filters, ...tz() } });
export const getSavingsRate = (filters: AnalyticsFilters = {}) =>
  apiRequest<SavingsRate>("/analytics/savings-rate", { query: { ...filters, ...tz() } });
export const getCategoryBreakdown = (
  kind: "expense" | "income" = "expense",
  filters: AnalyticsFilters = {},
) =>
  apiRequest<CategoryBreakdown>("/analytics/category-breakdown", {
    query: { kind, ...filters, ...tz() },
  });
export const getMonthly = (year: number, currency?: string) =>
  apiRequest<Monthly>("/analytics/monthly", { query: { year, currency, ...tz() } });
export const getComparison = (month?: string, currency?: string) =>
  apiRequest<Comparison>("/analytics/comparison", { query: { month, currency, ...tz() } });

// ---------------------------------------------------------------- deposits

export const listDeposits = (options: { limit?: number; offset?: number } = {}) =>
  apiRequest<Page<Deposit>>("/deposits", { query: options });
export const getDeposit = (id: number) => apiRequest<Deposit>(`/deposits/${id}`);
export type DepositInput = {
  bank_id: number;
  principal: string;
  currency?: string;
  interest_rate: string;
  effective_rate?: string | null;
  capitalization: Capitalization;
  start_date: string;
  end_date: string;
};
export const createDeposit = (input: DepositInput) =>
  apiRequest<Deposit>("/deposits", { method: "POST", json: input });
export const updateDeposit = (id: number, patch: Partial<DepositInput>) =>
  apiRequest<Deposit>(`/deposits/${id}`, { method: "PATCH", json: patch });
export const deleteDeposit = (id: number) =>
  apiRequest<void>(`/deposits/${id}`, { method: "DELETE" });
export type DepositCalculationInput = {
  principal: string;
  currency?: string;
  interest_rate: string;
  capitalization: Capitalization;
  start_date: string;
  end_date?: string;
  term_months?: number;
};
export const calculateDeposit = (input: DepositCalculationInput) =>
  apiRequest<DepositCalculation>("/deposits/calculate", { method: "POST", json: input });

// ---------------------------------------------------------------- goals

export const listGoals = () => apiRequest<Goal[]>("/goals", { query: tz() });
export const getGoal = (id: number) => apiRequest<Goal>(`/goals/${id}`, { query: tz() });
export type GoalInput = {
  name: string;
  target_amount: string;
  saved_amount?: string;
  currency?: string;
  target_date?: string | null;
};
export const createGoal = (input: GoalInput) =>
  apiRequest<Goal>("/goals", { method: "POST", json: input, query: tz() });
export const updateGoal = (id: number, patch: Partial<Omit<GoalInput, "currency">>) =>
  apiRequest<Goal>(`/goals/${id}`, { method: "PATCH", json: patch, query: tz() });
export const deleteGoal = (id: number) => apiRequest<void>(`/goals/${id}`, { method: "DELETE" });

// ---------------------------------------------------------------- AI advisor

export const askAdvisor = (question: string, currency?: string) =>
  apiRequest<AdvisorAnswer>("/advisor/ask", {
    method: "POST",
    json: { question },
    query: { currency, ...tz() },
  });
export const getAdvisorReport = (currency?: string) =>
  apiRequest<AdvisorReport>("/advisor/insights", { method: "POST", query: { currency, ...tz() } });

// ---------------------------------------------------------------- imports

export const listImportBanks = () => apiRequest<ImportBank[]>("/imports/banks");
export type ImportPreview = { import: ImportSummary; rows: ImportRow[]; verified_parser: boolean };
export const previewImport = (bank: string, file: File, accountId?: number | null) => {
  const form = new FormData();
  form.set("file", file);
  if (accountId) form.set("account_id", String(accountId));
  return apiRequest<ImportPreview>(`/imports/${encodeURIComponent(bank)}/preview`, {
    method: "POST",
    form,
  });
};
export const listImportRows = (
  id: number,
  options: { status?: ImportRow["status"]; limit?: number; offset?: number } = {},
) => apiRequest<Page<ImportRow>>(`/imports/${id}/rows`, { query: options });
export const commitImport = (
  id: number,
  input: { exclude_rows?: number[]; include_possible_duplicates?: boolean } = {},
) =>
  apiRequest<{ import: ImportSummary; imported: number; skipped: number }>(
    `/imports/${id}/commit`,
    { method: "POST", json: input },
  );
export const deleteImport = (id: number) =>
  apiRequest<void>(`/imports/${id}`, { method: "DELETE" });
export const listImports = (options: { limit?: number; offset?: number } = {}) =>
  apiRequest<Page<ImportSummary>>("/imports", { query: options });
export const getImport = (id: number) => apiRequest<ImportSummary>(`/imports/${id}`);
