/**
 * Pure helpers for the deposit screens (DP-1…DP-3): input normalisation and
 * validation without floating-point arithmetic, labels and assumption texts.
 */
import type { FieldError } from "@/lib/api/errors";
import type { Capitalization, DepositDataIssue } from "@/lib/types";

export const CAPITALIZATION_LABELS: Record<Capitalization, string> = {
  none: "Без капитализации",
  monthly: "Ежемесячно",
  quarterly: "Ежеквартально",
  annually: "Ежегодно",
};

/** Shown instead of the estimate for a stored deposit with a `data_issue`. */
export const DATA_ISSUE_LABELS: Record<DepositDataIssue, string> = {
  invalid_date_range: "Дата окончания не позже даты начала.",
  date_out_of_range: "Даты вне допустимого диапазона 01.01.1900 — 31.12.2200.",
  term_too_long: "Срок больше 600 месяцев (50 лет).",
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

/*
 * Deposit term rules mirrored from the backend (T4,
 * `app/services/finance/deposit.py::deposit_term_issue`). The backend stays
 * authoritative; these checks only give an early, field-specific message.
 */
export const MIN_DEPOSIT_DATE = "1900-01-01";
export const MAX_DEPOSIT_DATE = "2200-12-31";
export const MAX_DEPOSIT_TERM_MONTHS = 600;

export const DATE_TOO_EARLY = "Дата не может быть раньше 01.01.1900.";
export const DATE_TOO_LATE = "Дата не может быть позже 31.12.2200.";
export const DATE_INVALID = "Введите корректную дату.";
export const END_NOT_AFTER_START = "Дата окончания должна быть позже даты начала.";
export const TERM_TOO_LONG = "Срок вклада — не больше 600 месяцев (50 лет).";
export const MATURITY_TOO_LATE = "Дата окончания вклада не может быть позже 31.12.2200.";
/** For a backend schema error without a field (`loc: []`): the term rules as a whole. */
export const TERM_RULES =
  "Проверьте даты: окончание позже начала, срок — не больше 600 месяцев, даты — с 01.01.1900 по 31.12.2200.";

const ISO_DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

/** Error text for one `YYYY-MM-DD` date outside 1900-01-01..2200-12-31, or null. */
export function dateBoundError(value: string): string | null {
  if (!ISO_DATE_RE.test(value)) return DATE_INVALID;
  // Fixed-width ISO dates compare correctly as strings.
  if (value < MIN_DEPOSIT_DATE) return DATE_TOO_EARLY;
  if (value > MAX_DEPOSIT_DATE) return DATE_TOO_LATE;
  return null;
}

/**
 * `YYYY-MM-DD` shifted by whole months, clamped to the month end
 * (31 Jan + 1 = 28/29 Feb) — integer arithmetic, same as backend `add_months`.
 */
export function addMonthsIso(value: string, months: number): string {
  const match = ISO_DATE_RE.exec(value);
  if (!match) throw new Error("addMonthsIso: expected YYYY-MM-DD");
  const index = Number(match[2]) - 1 + months;
  const year = Number(match[1]) + Math.floor(index / 12);
  const month = (((index % 12) + 12) % 12) + 1;
  const leap = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
  const lastDay = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1];
  const day = Math.min(Number(match[3]), lastDay);
  const pad = (n: number, width: number) => String(n).padStart(width, "0");
  return `${pad(year, 4)}-${pad(month, 2)}-${pad(day, 2)}`;
}

/** True when the term from `start` to `end` is longer than 600 months. */
export function termTooLong(start: string, end: string): boolean {
  return end > addMonthsIso(start, MAX_DEPOSIT_TERM_MONTHS);
}

/** Start/end dates (`YYYY-MM-DD`): within bounds, end after start, term ≤ 600 months. */
export function dateRangeError(start: string, end: string): { start?: string; end?: string } {
  const errors: { start?: string; end?: string } = {};
  if (!start) errors.start = "Укажите дату начала.";
  else errors.start = dateBoundError(start) ?? undefined;
  if (!end) errors.end = "Укажите дату окончания.";
  else errors.end = dateBoundError(end) ?? undefined;
  if (start && end && !errors.start && !errors.end) {
    if (end <= start) errors.end = END_NOT_AFTER_START;
    else if (termTooLong(start, end)) errors.end = TERM_TOO_LONG;
  }
  if (!errors.start) delete errors.start;
  if (!errors.end) delete errors.end;
  return errors;
}

/**
 * Russian messages for backend 422 issues on a deposit form. Date bounds
 * arrive as generic `greater_than_equal` / `less_than_equal` issues, and the
 * term rule as a model-level issue without a field (`"_"`, from `loc: []`),
 * which is shown on `termField` (the field the user sets the end with).
 */
export function depositFieldErrors(
  items: FieldError[],
  termField: string,
): { field: string; message: string }[] {
  return items.map((item) => {
    if (item.field === "_") return { field: termField, message: TERM_RULES };
    if (item.field === "start_date" || item.field === "end_date") {
      if (item.type === "greater_than_equal") return { field: item.field, message: DATE_TOO_EARLY };
      if (item.type === "less_than_equal") return { field: item.field, message: DATE_TOO_LATE };
    }
    return { field: item.field, message: item.message };
  });
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
