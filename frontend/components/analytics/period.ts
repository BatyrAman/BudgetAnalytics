/**
 * Pure period helpers for the analytics filters (AN-1, AN-2).
 *
 * All dates are local calendar dates `YYYY-MM-DD` in the user's IANA time zone;
 * `date_from` / `date_to` sent to the API are inclusive. No financial math here.
 * Zone primitives come from `@/lib/timezone` (single source).
 */
import {
  localDayEnd,
  localDayStart,
  offsetMinutes,
  parseLocalDate,
  todayInTimezone,
} from "@/lib/timezone";

export { offsetMinutes, todayInTimezone };

export type PeriodPreset = "month" | "previous" | "quarter" | "year" | "custom";
export type DateRange = { from: string; to: string };

export const PERIOD_PRESETS: readonly (readonly [PeriodPreset, string])[] = [
  ["month", "Этот месяц"],
  ["previous", "Прошлый месяц"],
  ["quarter", "3 месяца"],
  ["year", "Год"],
  ["custom", "Свой период"],
];

const pad = (value: number, size = 2) => String(value).padStart(size, "0");

export function isIsoDate(value: string | null | undefined): value is string {
  return Boolean(value && parseLocalDate(value));
}

/** Number of days in a month (`month` is 1-based). */
export function daysInMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

const isoDate = (year: number, month: number, day: number) =>
  `${pad(year, 4)}-${pad(month)}-${pad(day)}`;

/** Inclusive date range for a preset, relative to the local date `today`. */
export function presetRange(preset: Exclude<PeriodPreset, "custom">, today: string): DateRange {
  const [year, month] = today.split("-").map(Number);
  const monthRange = (y: number, m: number): DateRange => ({
    from: isoDate(y, m, 1),
    to: isoDate(y, m, daysInMonth(y, m)),
  });
  switch (preset) {
    case "month":
      return monthRange(year, month);
    case "previous":
      return month === 1 ? monthRange(year - 1, 12) : monthRange(year, month - 1);
    case "quarter": {
      // The current month plus the two before it.
      const startMonthIndex = year * 12 + (month - 1) - 2;
      const startYear = Math.floor(startMonthIndex / 12);
      const startMonth = (startMonthIndex % 12) + 1;
      return { from: isoDate(startYear, startMonth, 1), to: monthRange(year, month).to };
    }
    case "year":
      return { from: isoDate(year, 1, 1), to: isoDate(year, 12, 31) };
  }
}

/** `YYYY-MM` of a local date (used for `/analytics/comparison?month=`). */
export const monthOf = (date: string) => date.slice(0, 7);
/** Calendar year of a local date (used for `/analytics/monthly?year=`). */
export const yearOf = (date: string) => Number(date.slice(0, 4));

/**
 * ISO datetime with the zone's offset for the start or the inclusive end of a
 * local day, e.g. `2026-11-30T23:59:59.999999+05:00`.
 */
export function localDayBoundary(date: string, edge: "start" | "end", timeZone: string): string {
  const value = edge === "start" ? localDayStart(date, timeZone) : localDayEnd(date, timeZone);
  if (!value) throw new RangeError(`Invalid local date: ${date}`);
  return value;
}

/** Link to the transactions list filtered by category and the analytics period. */
export function transactionsHref(categoryId: number, range: DateRange, timeZone: string): string {
  const params = new URLSearchParams({
    category_id: String(categoryId),
    start_date: localDayBoundary(range.from, "start", timeZone),
    end_date: localDayBoundary(range.to, "end", timeZone),
  });
  return `/transactions?${params.toString()}`;
}
