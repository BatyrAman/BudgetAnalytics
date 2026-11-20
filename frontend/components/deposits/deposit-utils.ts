/**
 * Pure helpers for the deposit screens (DP-1…DP-3): input normalisation and
 * validation without floating-point arithmetic, labels and assumption texts.
 */
import type { Capitalization } from "@/lib/types";

export const CAPITALIZATION_LABELS: Record<Capitalization, string> = {
  none: "Без капитализации",
  monthly: "Ежемесячно",
  quarterly: "Ежеквартально",
  annually: "Ежегодно",
};

/** No currency list endpoint exists (G-5): static list of the backend's currencies. */
export const SUPPORTED_CURRENCIES = ["KZT", "USD", "EUR", "RUB"] as const;

export const bankInitials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toLocaleUpperCase("ru");

/** Removes spaces and turns a decimal comma into a dot; does not alter digits. */
export const normalizeDecimal = (value: string) =>
  value
    .trim()
    .replace(/[\s\u00a0]/g, "")
    .replace(",", ".");

const MONEY_RE = /^\d{1,13}(\.\d{1,2})?$/;
const NOMINAL_RATE_RE = /^(100(\.0{1,2})?|\d{1,2}(\.\d{1,2})?)$/;
const EFFECTIVE_RATE_RE = /^(1000(\.0{1,4})?|\d{1,3}(\.\d{1,4})?)$/;

/** Error text for a principal (> 0, up to 2 decimals), or null when valid. */
export function principalError(raw: string): string | null {
  const value = normalizeDecimal(raw);
  if (!value) return "Укажите сумму.";
  if (!MONEY_RE.test(value)) return "Введите сумму числом, не больше 2 знаков после запятой.";
  if (!/[1-9]/.test(value)) return "Сумма должна быть больше нуля.";
  return null;
}

/** Nominal annual rate: 0–100 %, up to 2 decimals. */
export function nominalRateError(raw: string): string | null {
  const value = normalizeDecimal(raw);
  if (!value) return "Укажите ставку.";
  if (!NOMINAL_RATE_RE.test(value))
    return "Ставка — от 0 до 100 %, не больше 2 знаков после запятой.";
  return null;
}

/** ГЭСВ as published by the bank: optional, 0–1000 %, up to 4 decimals. */
export function effectiveRateError(raw: string): string | null {
  const value = normalizeDecimal(raw);
  if (!value) return null;
  if (!EFFECTIVE_RATE_RE.test(value))
    return "ГЭСВ — от 0 до 1000 %, не больше 4 знаков после запятой.";
  return null;
}

/** Term in months: integer 1–600. */
export function termMonthsError(raw: string): string | null {
  const value = raw.trim();
  if (!value) return "Укажите срок в месяцах.";
  if (!/^\d{1,3}$/.test(value)) return "Срок — целое число месяцев от 1 до 600.";
  const months = Number(value);
  if (months < 1 || months > 600) return "Срок — целое число месяцев от 1 до 600.";
  return null;
}

/** Start/end dates (`YYYY-MM-DD`); the end must be after the start. */
export function dateRangeError(start: string, end: string): { start?: string; end?: string } {
  const errors: { start?: string; end?: string } = {};
  if (!start) errors.start = "Укажите дату начала.";
  if (!end) errors.end = "Укажите дату окончания.";
  if (start && end && end <= start) errors.end = "Дата окончания должна быть позже даты начала.";
  return errors;
}

/** Rate with all decimals returned by the API (no truncation), e.g. «17,2271 %». */
export function formatRateExact(value: string): string {
  const negative = value.startsWith("-");
  const [whole, fraction = ""] = value.replace(/^[+-]/, "").split(".");
  return `${negative ? "−" : ""}${whole}${fraction ? `,${fraction}` : ""}\u00a0%`;
}

/**
 * Russian versions of the assumptions returned by the backend
 * (`app/schemas/deposits.py::ASSUMPTIONS`). Matched by exact text; any other
 * text is shown as-is under «Допущения backend».
 */
const ASSUMPTION_TRANSLATIONS: Record<string, string> = {
  "Nominal rate, ACT/365 day count; interest rounded once to the currency minor unit (half up).":
    "Номинальная ставка, база ACT/365; проценты округляются один раз до минимальной единицы валюты (половина вверх).",
  "Capitalization on monthly/quarterly/annual anniversaries of the start date; simple interest for the remaining days.":
    "Капитализация в ежемесячные / ежеквартальные / ежегодные даты-«годовщины» начала вклада; на оставшиеся дни — простые проценты.",
  "No top-ups, withdrawals, fees, taxes or early-termination rules are modelled; the bank's figures may differ.":
    "Пополнения, снятия, комиссии, налоги и правила досрочного расторжения не учитываются; расчёт банка может отличаться.",
};

export function translateAssumptions(items: string[]): { known: string[]; unknown: string[] } {
  const known: string[] = [];
  const unknown: string[] = [];
  for (const item of items) {
    const translated = ASSUMPTION_TRANSLATIONS[item.trim()];
    if (translated) known.push(translated);
    else unknown.push(item);
  }
  return { known, unknown };
}
