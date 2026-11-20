/**
 * Calendar-month helpers in the user's IANA time zone. Only date arithmetic —
 * no money is computed here.
 */
import { formatMonth } from "@/lib/format";
import { localDayEnd, localDayStart } from "@/lib/timezone";

export { currentMonth } from "@/lib/timezone";

function parseMonth(month: string): { year: number; month: number } {
  const [year, value] = month.split("-").map(Number);
  return { year, month: value };
}

export function shiftMonth(month: string, delta: number): string {
  const { year, month: value } = parseMonth(month);
  const index = year * 12 + (value - 1) + delta;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`;
}

/** Inclusive bounds of a calendar month in `timeZone`, as ISO with the zone offset (for `/transactions`). */
export function monthBounds(month: string, timeZone: string): { start: string; end: string } {
  const { year, month: value } = parseMonth(month);
  const lastDay = new Date(Date.UTC(year, value, 0)).getUTCDate();
  const start = localDayStart(`${month}-01`, timeZone);
  const end = localDayEnd(`${month}-${String(lastDay).padStart(2, "0")}`, timeZone);
  if (!start || !end) throw new RangeError(`Invalid month: ${month}`);
  return { start, end };
}

/** «Ноябрь 2026». */
export function monthLabel(month: string): string {
  const label = formatMonth(month);
  return label.charAt(0).toLocaleUpperCase("ru") + label.slice(1);
}

/** Last `count` months ending with `last`, newest last. */
export function recentMonths(last: string, count: number): string[] {
  return Array.from({ length: count }, (_, index) => shiftMonth(last, index - count + 1));
}
