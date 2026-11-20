/**
 * Transaction list filters: types, labels and the URL query <-> filter mapping.
 * The URL is the single source of truth for the T-1 list, so links from
 * Analytics/Budgets (`/transactions?category_id=3&start_date=…`) and a page
 * refresh keep the same filters.
 */
import type { TransactionFilters } from "@/lib/api/client";
import type { Category, TransactionType } from "@/lib/types";

import { localDayEnd, localDayStart } from "./period";

export const TRANSACTION_TYPES: TransactionType[] = [
  "expense",
  "income",
  "refund",
  "transfer_in",
  "transfer_out",
];

export const TYPE_LABELS: Record<TransactionType, string> = {
  expense: "Расход",
  income: "Доход",
  refund: "Возврат",
  transfer_in: "Перевод: поступление",
  transfer_out: "Перевод: списание",
};

/** Static currency list (no currency endpoint exists — G-5). */
export const CURRENCY_CHOICES = ["KZT", "USD", "EUR", "RUB"];

export const PAGE_SIZES = [20, 50, 100] as const;
export type PageSize = (typeof PAGE_SIZES)[number];
export const DEFAULT_PAGE_SIZE: PageSize = 20;

/** User-editable list filters (everything except pagination). */
export type ListFilters = Omit<TransactionFilters, "limit" | "offset">;
export type ListPage = { limit: PageSize; offset: number };

/** Category kinds allowed for a transaction type (mirrors backend `category_kind_mismatch`). */
export function isCategoryAllowed(category: Pick<Category, "kind">, type: TransactionType) {
  if (type === "income") return category.kind === "income" || category.kind === "any";
  if (type === "expense" || type === "refund")
    return category.kind === "expense" || category.kind === "any";
  return true;
}

export function categoriesForType(categories: Category[], type: TransactionType): Category[] {
  return categories.filter((category) => isCategoryAllowed(category, type));
}

const AMOUNT_RE = /^\d{1,16}(\.\d{1,2})?$/;
const CURRENCY_RE = /^[A-Z]{3}$/;
const DATE_ONLY_RE = /^\d{4}-\d{2}-\d{2}$/;

function positiveInt(value: string | null): number | undefined {
  if (!value || !/^\d{1,9}$/.test(value)) return undefined;
  const parsed = Number(value);
  return parsed > 0 ? parsed : undefined;
}

function dateParam(value: string | null, edge: "start" | "end", timeZone: string) {
  if (!value) return undefined;
  if (DATE_ONLY_RE.test(value)) {
    return (
      (edge === "start" ? localDayStart(value, timeZone) : localDayEnd(value, timeZone)) ??
      undefined
    );
  }
  return Number.isNaN(new Date(value).getTime()) ? undefined : value;
}

function isTransactionType(value: string | null): value is TransactionType {
  return value !== null && (TRANSACTION_TYPES as string[]).includes(value);
}

/** Read filters and page from a URL query. Invalid values are ignored. */
export function parseListQuery(
  params: URLSearchParams,
  timeZone: string,
): { filters: ListFilters; page: ListPage } {
  const filters: ListFilters = {};
  const start = dateParam(params.get("start_date"), "start", timeZone);
  const end = dateParam(params.get("end_date"), "end", timeZone);
  if (start) filters.start_date = start;
  if (end) filters.end_date = end;
  const categoryId = positiveInt(params.get("category_id"));
  const accountId = positiveInt(params.get("account_id"));
  const bankId = positiveInt(params.get("bank_id"));
  if (categoryId) filters.category_id = categoryId;
  if (accountId) filters.account_id = accountId;
  if (bankId) filters.bank_id = bankId;
  const type = params.get("transaction_type");
  if (isTransactionType(type)) filters.transaction_type = type;
  const currency = params.get("currency");
  if (currency && CURRENCY_RE.test(currency)) filters.currency = currency;
  const min = params.get("min_amount");
  const max = params.get("max_amount");
  if (min && AMOUNT_RE.test(min)) filters.min_amount = min;
  if (max && AMOUNT_RE.test(max)) filters.max_amount = max;
  const search = params.get("search")?.trim();
  if (search) filters.search = search.slice(0, 100);

  const limitParam = Number(params.get("limit"));
  const limit = (PAGE_SIZES as readonly number[]).includes(limitParam)
    ? (limitParam as PageSize)
    : DEFAULT_PAGE_SIZE;
  const offsetParam = params.get("offset");
  const offset = offsetParam && /^\d{1,9}$/.test(offsetParam) ? Number(offsetParam) : 0;
  return { filters, page: { limit, offset } };
}

const KEY_ORDER: (keyof ListFilters)[] = [
  "start_date",
  "end_date",
  "transaction_type",
  "category_id",
  "account_id",
  "bank_id",
  "currency",
  "min_amount",
  "max_amount",
  "search",
];

/** Serialize filters/page to a query string (stable key order, defaults omitted). */
export function buildListQuery(filters: ListFilters, page: ListPage): string {
  const params = new URLSearchParams();
  for (const key of KEY_ORDER) {
    const value = filters[key];
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  if (page.limit !== DEFAULT_PAGE_SIZE) params.set("limit", String(page.limit));
  if (page.offset > 0) params.set("offset", String(page.offset));
  return params.toString();
}

export function countActiveFilters(filters: ListFilters): number {
  const { start_date, end_date, ...rest } = filters;
  const period = start_date || end_date ? 1 : 0;
  return period + Object.values(rest).filter((value) => value !== undefined && value !== "").length;
}

/** Compare two non-negative decimal strings without converting them to floats. */
export function compareDecimal(a: string, b: string): number {
  const [aWhole = "0", aFraction = ""] = a.split(".");
  const [bWhole = "0", bFraction = ""] = b.split(".");
  const aw = aWhole.replace(/^0+(?=\d)/, "");
  const bw = bWhole.replace(/^0+(?=\d)/, "");
  if (aw.length !== bw.length) return aw.length < bw.length ? -1 : 1;
  if (aw !== bw) return aw < bw ? -1 : 1;
  const af = aFraction.padEnd(2, "0");
  const bf = bFraction.padEnd(2, "0");
  if (af === bf) return 0;
  return af < bf ? -1 : 1;
}

/** True when both bounds are set and min > max (backend would answer `invalid_amount_range`). */
export function isAmountRangeInvalid(min?: string, max?: string): boolean {
  if (!min || !max) return false;
  return compareDecimal(min, max) > 0;
}
