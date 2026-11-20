"use client";

import {
  TransactionsList,
  type FixedTransactionFilters,
} from "@/components/transactions/transactions-list";
import type { Budget } from "@/lib/types";

import { monthBounds } from "./month";

/** Expense operations of the budget's category (or all), currency and month (B-2). */
export function budgetTransactionFilters(
  budget: Budget,
  month: string,
  timeZone: string,
): FixedTransactionFilters {
  const { start, end } = monthBounds(month, timeZone);
  return {
    ...(budget.category_id === null ? {} : { category_id: budget.category_id }),
    transaction_type: "expense",
    currency: budget.currency_code,
    start_date: start,
    end_date: end,
  };
}

export function BudgetTransactions({
  budget,
  month,
  timeZone,
}: {
  budget: Budget;
  month: string;
  timeZone: string;
}) {
  return (
    <TransactionsList
      filters={budgetTransactionFilters(budget, month, timeZone)}
      emptyDescription="В этом месяце расходов по бюджету нет."
    />
  );
}
