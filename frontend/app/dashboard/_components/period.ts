import { currentMonth } from "@/lib/timezone";

/** Current calendar year and month (YYYY-MM) in the given IANA time zone. */
export function currentYearMonth(
  timeZone: string,
  now: Date = new Date(),
): { year: number; month: string } {
  const month = currentMonth(timeZone, now);
  return { year: Number(month.slice(0, 4)), month };
}
