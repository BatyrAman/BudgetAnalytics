"use client";

import { useSWRConfig } from "swr";

import { CategoryIcon } from "@/components/categories/category-icons";
import type { Budget, Category } from "@/lib/types";

const BUDGET_KEYS = new Set(["budgets", "budget", "budget-utilization", "overview"]);

/** Revalidate budget lists, details, usage and the dashboard after a mutation. */
export function useRevalidateBudgets() {
  const { mutate } = useSWRConfig();
  return () => mutate((key) => Array.isArray(key) && BUDGET_KEYS.has(String(key[0])));
}

export function BudgetCategory({
  budget,
  categories,
}: {
  budget: Budget;
  categories: Category[] | undefined;
}) {
  const category = categories?.find((item) => item.id === budget.category_id);
  const name =
    budget.category_id === null
      ? "Все расходы"
      : (category?.name ?? (categories ? "Категория недоступна" : "…"));
  return (
    <span className="budget-category">
      <CategoryIcon
        icon={category?.icon ?? "wallet"}
        color={category?.color}
        className="budget-category-icon"
      />
      {name}
    </span>
  );
}
