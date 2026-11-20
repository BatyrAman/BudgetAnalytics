import { Banknote, CreditCard, Landmark, Wallet } from "lucide-react";
import { localDayStart, todayInTimezone } from "@/lib/timezone";
import { parseAmountInput } from "@/lib/format";
import type { AccountType } from "@/lib/types";

export const accountTypeLabels: Record<AccountType, string> = {
  cash: "Наличные",
  current: "Текущий счёт",
  card: "Карта",
  savings: "Сберегательный",
  credit_card: "Кредитная карта",
  other: "Другое",
};

export const accountTypeIcons: Record<AccountType, typeof Wallet> = {
  cash: Banknote,
  current: Landmark,
  card: CreditCard,
  savings: Landmark,
  credit_card: CreditCard,
  other: Wallet,
};

export const isAccountType = (value: string): value is AccountType => value in accountTypeLabels;

/** Static currency list for pickers (no currency list endpoint exists — G-5). */
export const STATIC_CURRENCIES = ["KZT", "USD", "EUR", "RUB"] as const;

/** Default currency first, then the rest alphabetically, without duplicates. */
export function orderCurrencies(codes: Iterable<string>, defaultCurrency: string): string[] {
  const rest = new Set(codes);
  const hasDefault = rest.delete(defaultCurrency);
  return [...(hasDefault ? [defaultCurrency] : []), ...[...rest].sort()];
}

/** SWR cache keys that depend on accounts (lists, details, overview totals). */
export const accountDependentKey = (key: unknown) =>
  Array.isArray(key) && ["accounts", "account", "overview"].includes(String(key[0]));

/** Calendar date (YYYY-MM-DD) of `instant` in the given time zone. */
export function dateInZone(timeZone: string, instant: Date = new Date()): string {
  return todayInTimezone(timeZone, instant);
}

/** ISO datetime of the start of `date` (YYYY-MM-DD) in the given time zone, e.g. `2026-11-01T00:00:00+05:00`. */
export function startOfDayIso(date: string, timeZone: string): string {
  const value = localDayStart(date, timeZone);
  if (!value) throw new RangeError(`Invalid local date: ${date}`);
  return value;
}

/**
 * Validate a signed money input (opening balance may be negative for a debt) and
 * return a decimal string for the API ("-1500.50"), or null when invalid.
 */
export function parseSignedAmount(raw: string): string | null {
  const compact = raw.replace(/[\s ]/g, "").replace("−", "-").replace(",", ".");
  if (!/^[-+]?\d+(\.\d{1,2})?$/.test(compact)) return null;
  const negative = compact.startsWith("-");
  const unsigned = parseAmountInput(compact.replace(/^[-+]/, ""));
  return negative && /[1-9]/.test(unsigned) ? `-${unsigned}` : unsigned;
}

/** Canonical 2-decimal string representation, for change detection only (no arithmetic). */
export function canonicalAmount(value: string): string {
  const negative = value.startsWith("-");
  const [whole = "0", fraction = ""] = value.replace(/^[-+]/, "").split(".");
  const normalizedWhole = whole.replace(/^0+(?=\d)/, "");
  return `${negative ? "-" : ""}${normalizedWhole}.${fraction.padEnd(2, "0").slice(0, 2)}`;
}
