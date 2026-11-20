"use client";

/**
 * Typed SWR hooks. Each hook builds its cache key and fetcher together, so a
 * cache key can never be passed to the API as an argument by mistake.
 * Components must use these hooks (or the client for mutations), never `fetch`.
 */
import useSWR, { type SWRConfiguration } from "swr";

import * as api from "./client";
import { ApiError } from "./errors";
import type { AnalyticsFilters, TransactionFilters } from "./client";
import type { ImportRow } from "@/lib/types";

const defaults: SWRConfiguration = {
  // Retry only failures that can succeed on repeat (network, 429, 5xx).
  shouldRetryOnError: (error: unknown) => error instanceof ApiError && error.retryable,
  errorRetryCount: 2,
  revalidateOnFocus: false,
};

export function useMe() {
  return useSWR(["me"], () => api.getMe(), defaults);
}

/** User's default currency (G-4); KZT until the profile is loaded. */
export function useDefaultCurrency(): string {
  const { data } = useMe();
  return data?.default_currency_code ?? "KZT";
}

export function useCategories(kind?: "income" | "expense") {
  return useSWR(["categories", kind ?? "all"], () => api.listCategories(kind), defaults);
}

export function useAccounts(includeArchived = false) {
  return useSWR(["accounts", includeArchived], () => api.listAccounts(includeArchived), defaults);
}

export function useAccount(id: number | null) {
  return useSWR(id ? ["account", id] : null, () => api.getAccount(id as number), defaults);
}

export function useBanks() {
  return useSWR(["banks"], () => api.listBanks(), { ...defaults, revalidateIfStale: false });
}

export function useTransactions(filters: TransactionFilters) {
  return useSWR(["transactions", filters], () => api.listTransactions(filters), {
    ...defaults,
    keepPreviousData: true,
  });
}

export function useTransaction(id: number | null) {
  return useSWR(id ? ["transaction", id] : null, () => api.getTransaction(id as number), defaults);
}

export function useBudgets(page: { limit: number; offset: number }) {
  return useSWR(["budgets", page.limit, page.offset], () => api.listBudgets(page), {
    ...defaults,
    keepPreviousData: true,
  });
}

export function useBudget(id: number | null) {
  return useSWR(id ? ["budget", id] : null, () => api.getBudget(id as number), defaults);
}

/** Usage of all budgets for a month (G-6) — one request for the whole list. */
export function useBudgetUtilizations(month?: string) {
  return useSWR(
    ["budget-utilization", month ?? "current"],
    () => api.listBudgetUtilization(month),
    defaults,
  );
}

export function useBudgetUtilization(id: number | null, month?: string) {
  return useSWR(
    id ? ["budget-utilization", id, month ?? "current"] : null,
    () => api.getBudgetUtilization(id as number, month),
    defaults,
  );
}

export function useOverview(currency?: string) {
  return useSWR(["overview", currency ?? "default"], () => api.getOverview(currency), defaults);
}

export function useSummary(filters: AnalyticsFilters) {
  return useSWR(["summary", filters], () => api.getSummary(filters), defaults);
}

export function useSavingsRate(filters: AnalyticsFilters) {
  return useSWR(["savings-rate", filters], () => api.getSavingsRate(filters), defaults);
}

export function useCategoryBreakdown(kind: "expense" | "income", filters: AnalyticsFilters = {}) {
  return useSWR(
    ["category-breakdown", kind, filters],
    () => api.getCategoryBreakdown(kind, filters),
    defaults,
  );
}

export function useMonthly(year: number, currency?: string) {
  return useSWR(
    ["monthly", year, currency ?? "default"],
    () => api.getMonthly(year, currency),
    defaults,
  );
}

export function useComparison(month?: string, currency?: string) {
  return useSWR(
    ["comparison", month ?? "current", currency ?? "default"],
    () => api.getComparison(month, currency),
    defaults,
  );
}

export function useDeposits(page: { limit: number; offset: number }) {
  return useSWR(["deposits", page.limit, page.offset], () => api.listDeposits(page), {
    ...defaults,
    keepPreviousData: true,
  });
}

export function useDeposit(id: number | null) {
  return useSWR(id ? ["deposit", id] : null, () => api.getDeposit(id as number), defaults);
}

export function useGoals() {
  return useSWR(["goals"], () => api.listGoals(), defaults);
}

export function useGoal(id: number | null) {
  return useSWR(id ? ["goal", id] : null, () => api.getGoal(id as number), defaults);
}

export function useImportBanks() {
  return useSWR(["import-banks"], () => api.listImportBanks(), defaults);
}

export function useImports(page: { limit: number; offset: number }) {
  return useSWR(["imports", page.limit, page.offset], () => api.listImports(page), {
    ...defaults,
    keepPreviousData: true,
  });
}

export function useImportRows(
  id: number | null,
  options: { status?: ImportRow["status"]; limit: number; offset: number },
) {
  return useSWR(
    id ? ["import-rows", id, options.status ?? "all", options.limit, options.offset] : null,
    () => api.listImportRows(id as number, options),
    { ...defaults, keepPreviousData: true },
  );
}
