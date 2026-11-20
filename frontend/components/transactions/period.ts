/**
 * Pure date helpers for transaction filters and the transaction form.
 *
 * The API accepts `start_date`/`end_date`/`transaction_date` as ISO date-times;
 * a value without an offset is treated as UTC. To filter by the user's *local*
 * calendar days we always send an explicit offset of the user's IANA time zone,
 * e.g. `2026-11-01T00:00:00+05:00` … `2026-11-30T23:59:59.999999+05:00` for
 * Asia/Almaty. Zone primitives live in `@/lib/timezone` (single source).
 */

import {
  localDayEnd,
  localDayStart,
  parseLocalDate,
  zonedIso,
  zonedParts,
  type LocalDateParts,
} from "@/lib/timezone";

export { localDayEnd, localDayStart, zonedIso, zonedParts, type LocalDateParts };

export type DateRange = { start_date: string; end_date: string };

export type PeriodPreset = "this_month" | "last_month" | "three_months" | "year";

export const PERIOD_PRESETS: { id: PeriodPreset; label: string }[] = [
  { id: "this_month", label: "Этот месяц" },
  { id: "last_month", label: "Прошлый месяц" },
  { id: "three_months", label: "3 месяца" },
  { id: "year", label: "Год" },
];

const pad = (value: number, size = 2) => String(value).padStart(size, "0");

/** ISO date-time (any offset) → `YYYY-MM-DD` of that instant in `timeZone`; "" if invalid. */
export function toLocalDateInput(iso: string, timeZone: string): string {
  if (parseLocalDate(iso)) return iso;
  const instant = new Date(iso);
  if (Number.isNaN(instant.getTime())) return "";
  const p = zonedParts(instant, timeZone);
  return `${pad(p.year, 4)}-${pad(p.month)}-${pad(p.day)}`;
}

/** ISO date-time → value for `<input type="datetime-local">` in `timeZone`. */
export function toLocalDateTimeInput(iso: string, timeZone: string): string {
  const instant = new Date(iso);
  if (Number.isNaN(instant.getTime())) return "";
  const p = zonedParts(instant, timeZone);
  return `${pad(p.year, 4)}-${pad(p.month)}-${pad(p.day)}T${pad(p.hour)}:${pad(p.minute)}`;
}

const DATETIME_RE = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/;

/** `datetime-local` value (wall time in `timeZone`) → ISO with offset; null if invalid. */
export function fromLocalDateTimeInput(value: string, timeZone: string): string | null {
  const match = DATETIME_RE.exec(value);
  if (!match) return null;
  const date = parseLocalDate(`${match[1]}-${match[2]}-${match[3]}`);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6] ?? 0);
  if (!date || hour > 23 || minute > 59 || second > 59) return null;
  return zonedIso({ ...date, hour, minute, second }, timeZone);
}

function lastDayOfMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

/** Shift a (year, month) pair by `delta` months. */
function addMonths(year: number, month: number, delta: number) {
  const index = year * 12 + (month - 1) + delta;
  return { year: Math.floor(index / 12), month: (index % 12) + 1 };
}

/**
 * Inclusive range for a preset, in calendar months of the user's time zone:
 * - this_month: 1st … last day of the current month;
 * - last_month: the whole previous month;
 * - three_months: 1st of the month two months ago … last day of the current month;
 * - year: 1 January … 31 December of the current year.
 */
export function presetRange(preset: PeriodPreset, now: Date, timeZone: string): DateRange {
  const today = zonedParts(now, timeZone);
  const range = (from: { year: number; month: number }, to: { year: number; month: number }) => ({
    start_date: zonedIso({ ...from, day: 1 }, timeZone),
    end_date: zonedIso(
      { ...to, day: lastDayOfMonth(to.year, to.month), hour: 23, minute: 59, second: 59 },
      timeZone,
      "999999",
    ),
  });
  const current = { year: today.year, month: today.month };
  switch (preset) {
    case "this_month":
      return range(current, current);
    case "last_month": {
      const previous = addMonths(today.year, today.month, -1);
      return range(previous, previous);
    }
    case "three_months":
      return range(addMonths(today.year, today.month, -2), current);
    case "year":
      return range({ year: today.year, month: 1 }, { year: today.year, month: 12 });
  }
}

/** Which preset (if any) exactly matches a range — used to highlight the active preset. */
export function matchingPreset(
  range: Partial<DateRange>,
  now: Date,
  timeZone: string,
): PeriodPreset | null {
  if (!range.start_date || !range.end_date) return null;
  for (const { id } of PERIOD_PRESETS) {
    const candidate = presetRange(id, now, timeZone);
    if (candidate.start_date === range.start_date && candidate.end_date === range.end_date)
      return id;
  }
  return null;
}
