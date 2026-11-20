import { currentTimezone } from "./timezone";
import type { TransactionType } from "./types";

const symbols: Record<string, string> = {
  KZT: "₸",
  USD: "$",
  EUR: "€",
  RUB: "₽",
};
const NBSP = "\u00a0";
/**
 * Splits a decimal string from the API. Digits are never dropped or rounded here:
 * the backend already rounded the value (money to minor units, rates to 4 dp,
 * ratios to 2 dp), so the UI shows exactly what it received.
 */
function normalizedDecimal(value: string) {
  const cleaned = value.replace(/[\s\u00a0]/g, "").replace(",", ".");
  const negative = cleaned.startsWith("-");
  const unsigned = cleaned.replace(/^[+-]/, "");
  const [whole = "0", fraction = ""] = unsigned.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
  return {
    negative,
    whole: grouped,
    fraction: fraction.padEnd(2, "0"),
  };
}
export function formatMoney(
  amount: string,
  currency: string,
  opts: { hideZeroCents?: boolean; sign?: "+" | "−" | null } = {},
) {
  const parsed = normalizedDecimal(amount);
  const cents = opts.hideZeroCents && parsed.fraction === "00" ? "" : `,${parsed.fraction}`;
  const sign = opts.sign !== undefined ? (opts.sign ?? "") : parsed.negative ? "−" : "";
  return `${sign}${parsed.whole}${cents}${NBSP}${symbols[currency] ?? currency}`;
}
export function formatPercent(value: string | null, table = false) {
  if (value === null) return "—";
  const parsed = normalizedDecimal(value);
  const fraction = table ? parsed.fraction : parsed.fraction.replace(/0+$/, "");
  return `${parsed.negative ? "−" : ""}${parsed.whole}${fraction ? `,${fraction}` : ""}${NBSP}%`;
}
export function formatPp(value: string | null) {
  if (value === null) return "—";
  const parsed = normalizedDecimal(value);
  const fraction = parsed.fraction.replace(/0+$/, "");
  return `${parsed.negative ? "−" : "+"}${parsed.whole}${fraction ? `,${fraction}` : ""} п. п.`;
}
const dateOptions = (): Intl.DateTimeFormatOptions => ({
  timeZone: currentTimezone(),
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;

/**
 * Calendar dates (`YYYY-MM-DD`, e.g. deposit or goal dates) are shown as-is —
 * they are not instants and must not shift with the time zone. Datetimes (UTC
 * instants from the API) are shown in the user's time zone.
 */
export function formatDate(value: string) {
  const dateOnly = DATE_ONLY.exec(value);
  if (dateOnly) return `${dateOnly[3]}.${dateOnly[2]}.${dateOnly[1]}`;
  return new Intl.DateTimeFormat("ru-KZ", dateOptions()).format(new Date(value));
}

export function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("ru-KZ", {
    ...dateOptions(),
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  })
    .format(new Date(value))
    .replace(" г.", "");
}

export function formatMonth(value: string) {
  const [year, month] = value.split("-").map(Number);
  return new Intl.DateTimeFormat("ru-KZ", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  })
    .format(new Date(Date.UTC(year, month - 1, 1)))
    .replace(/\s+г\.$/, "");
}

export function formatPeriod(from: string, to: string) {
  const start = new Date(`${from.slice(0, 10)}T12:00:00Z`);
  const end = new Date(`${to.slice(0, 10)}T12:00:00Z`);
  const monthFormatter = new Intl.DateTimeFormat("ru-KZ", {
    month: "short",
    timeZone: "UTC",
  });
  const yearFormatter = new Intl.DateTimeFormat("ru-KZ", {
    year: "numeric",
    timeZone: "UTC",
  });
  const startMonth = monthFormatter.format(start);
  const endMonth = monthFormatter.format(end);
  const startYear = yearFormatter.format(start);
  const endYear = yearFormatter.format(end);
  const sameMonth = start.getUTCMonth() === end.getUTCMonth() && startYear === endYear;
  const sameYear = startYear === endYear;
  const endLabel = `${end.getUTCDate()} ${endMonth} ${endYear}`;

  if (sameMonth) return `${start.getUTCDate()}–${endLabel}`;
  if (sameYear) return `${start.getUTCDate()} ${startMonth} – ${endLabel}`;
  return `${start.getUTCDate()} ${startMonth} ${startYear} – ${endLabel}`;
}
export function signForType(type: TransactionType): "+" | "−" | null {
  return ["income", "refund", "transfer_in"].includes(type)
    ? "+"
    : ["expense", "transfer_out"].includes(type)
      ? "−"
      : null;
}
export function parseAmountInput(value: string) {
  return value
    .replace(/[\s\u00a0]/g, "")
    .replace(",", ".")
    .replace(/[^\d.]/g, "")
    .replace(/\.(?=.*\.)/g, "")
    .replace(/(\.\d{0,2}).*$/, "$1");
}
