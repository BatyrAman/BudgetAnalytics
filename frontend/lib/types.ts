export type TransactionType = "income" | "expense" | "refund" | "transfer_in" | "transfer_out";
export type CategoryKind = "income" | "expense" | "any";
export type AccountType = "cash" | "current" | "card" | "savings" | "credit_card" | "other";
export type Capitalization = "none" | "monthly" | "quarterly" | "annually";
export type Page<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};
export type User = {
  id: number;
  full_name: string;
  email: string;
  is_active: boolean;
  /** G-4: user's default currency (ISO 4217), KZT unless changed in the backend. */
  default_currency_code: string;
  created_at: string;
  updated_at: string;
};
export type Category = {
  id: number;
  name: string;
  color: string;
  icon: string;
  kind: CategoryKind;
  is_system: boolean;
};
export type Account = {
  id: number;
  name: string;
  account_type: AccountType;
  currency_code: string;
  bank_id: number | null;
  last4: string | null;
  is_archived: boolean;
  opening_balance: string;
  opening_balance_at: string;
  balance: string;
  created_at: string;
  updated_at: string;
};
export type Bank = { id: number; name: string; logo: string | null };
export type Transaction = {
  id: number;
  amount: string;
  currency_code: string;
  description: string | null;
  transaction_type: TransactionType;
  transaction_date: string;
  category_id: number;
  bank_id: number | null;
  account_id: number | null;
  created_at: string;
  updated_at: string;
};
export type TransactionDetail = Transaction & {
  category_name: string;
  bank_name: string;
};
export type Budget = {
  id: number;
  title: string;
  monthly_limit: string;
  currency_code: string;
  category_id: number | null;
};
export type BudgetUtilization = {
  budget_id: number;
  month: string;
  currency_code: string;
  limit: string;
  spent: string;
  remaining: string;
  utilization_percent: string;
  is_exceeded: boolean;
};
export type SavingsRate = {
  period: { date_from: string; date_to: string; timezone: string };
  currency_code: string;
  income: string;
  net_expenses: string;
  savings_rate: string | null;
  expense_to_income_percent: string | null;
};
export type IncomeSummary = {
  period: { date_from: string; date_to: string; timezone: string };
  currency_code: string;
  total: string;
  by_category: CategoryAmount[];
};
export type ExpenseSummary = {
  period: { date_from: string; date_to: string; timezone: string };
  currency_code: string;
  gross_expenses: string;
  refunds: string;
  net_expenses: string;
  by_category: CategoryAmount[];
};
export type Summary = {
  period: { date_from: string; date_to: string; timezone: string };
  currency_code: string;
  income: string;
  gross_expenses: string;
  refunds: string;
  net_expenses: string;
  net_cash_flow: string;
  transfers_in: string;
  transfers_out: string;
  savings_rate: string | null;
  transaction_count: number;
};
export type CategoryAmount = {
  category_id: number;
  name: string;
  amount: string;
  transaction_count: number;
  share_percent: string | null;
};
export type CategoryBreakdown = {
  period: Summary["period"];
  currency_code: string;
  kind: "expense" | "income";
  total: string;
  items: CategoryAmount[];
};
export type MonthSummary = {
  month: string;
  income: string;
  net_expenses: string;
  net_cash_flow: string;
  savings_rate: string | null;
  transaction_count: number;
};
export type Monthly = {
  year: number;
  timezone: string;
  currency_code: string;
  months: MonthSummary[];
  total: MonthSummary;
};
export type MetricChange = {
  current: string;
  previous: string;
  change: string;
  change_percent: string | null;
};
export type Comparison = {
  timezone: string;
  currency_code: string;
  current: MonthSummary;
  previous: MonthSummary;
  income: MetricChange;
  net_expenses: MetricChange;
  net_cash_flow: MetricChange;
  savings_rate_change_pp: string | null;
};
export type Overview = {
  generated_at: string;
  timezone: string;
  currency_code: string;
  month: string;
  current_balance: string | null;
  accounts: {
    account_id: number;
    name: string;
    currency_code: string;
    balance: string;
  }[];
  monthly_income: string;
  monthly_expenses: string;
  monthly_net_cash_flow: string;
  budgets: {
    budget_id: number;
    title: string;
    limit: string;
    spent: string;
    utilization_percent: string;
    is_exceeded: boolean;
  }[];
  indicators: {
    savings_rate: string | null;
    expense_to_income_percent: string | null;
    expense_change_percent: string | null;
    income_change_percent: string | null;
    average_monthly_expenses_3m: string | null;
    emergency_fund_months: string | null;
    budgets_exceeded: number;
    budgets_total: number;
    deposits_principal: string;
    deposits_expected_interest: string;
  };
};
export type Maturity = {
  term_days: number;
  capitalization_periods: number;
  stub_days: number;
  interest: string;
  maturity_amount: string;
  effective_annual_rate: string | null;
  assumptions: string[];
};
export type Deposit = {
  id: number;
  bank_id: number;
  principal: string;
  currency_code: string;
  interest_rate: string;
  effective_rate: string | null;
  capitalization: Capitalization;
  start_date: string;
  end_date: string;
  maturity: Maturity;
};
export type DepositCalculation = {
  principal: string;
  currency_code: string;
  interest_rate: string;
  capitalization: Capitalization;
  start_date: string;
  maturity_date: string;
  maturity: Maturity;
};
export type Goal = {
  id: number;
  name: string;
  currency_code: string;
  target_amount: string;
  saved_amount: string;
  target_date: string | null;
  progress_percent: string;
  remaining: string;
  is_reached: boolean;
  months_left: number | null;
  required_monthly_saving: string | null;
};
export type Fact = {
  id: string;
  topic: string;
  label: string;
  value: string;
  unit: string;
  period: string | null;
};
export type AdvisorMeta = {
  generated_by: "llm" | "rules";
  fallback_reason: "disabled" | "limit_reached" | "provider_error" | "invalid_output" | null;
  currency_code: string;
  as_of: string;
  facts: Fact[];
  disclaimers: string[];
};
export type AdvisorAnswer = AdvisorMeta & {
  answer: {
    answer: string;
    evidence: string[];
    assumptions: string[];
    involves_investment: boolean;
    needs_more_data: boolean;
    follow_up_question: string | null;
  };
};
export type AdvisorReport = AdvisorMeta & {
  report: {
    summary: string;
    insights: {
      area: string;
      title: string;
      explanation: string;
      evidence: string[];
    }[];
    recommendations: {
      title: string;
      action: string;
      reasoning: string;
      evidence: string[];
      assumptions: string[];
      priority: "high" | "medium" | "low";
      involves_investment: boolean;
    }[];
    risks: {
      title: string;
      explanation: string;
      severity: "high" | "medium" | "low";
      evidence: string[];
    }[];
    assumptions: string[];
    data_gaps: string[];
  };
};
export type ImportBank = {
  code: "kaspi" | "halyk" | "freedom";
  name: string;
  formats: string[];
  verified: boolean;
};
export type ImportSummary = {
  id: number;
  bank: string;
  file_name: string;
  file_format: string;
  file_size: number;
  status: "preview" | "committed" | "failed" | "cancelled" | "expired";
  account_id: number | null;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  duplicate_rows: number;
  imported_rows: number;
  period_start: string | null;
  period_end: string | null;
  error_message: string | null;
  created_at: string;
  expires_at: string | null;
};
export type ImportRow = {
  row_number: number;
  status: "valid" | "invalid" | "duplicate" | "possible_duplicate" | "imported" | "skipped";
  transaction_date: string | null;
  amount: string | null;
  currency_code: string | null;
  transaction_type: TransactionType | null;
  description: string | null;
  merchant: string | null;
  category_hint: string | null;
  error_message: string | null;
};
