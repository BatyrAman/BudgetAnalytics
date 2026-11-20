import { afterEach, describe, expect, it, vi } from "vitest";

import {
  DEFAULT_TIMEZONE,
  TIMEZONE_EVENT,
  currentMonth,
  currentTimezone,
  localDayEnd,
  localDayStart,
  offsetMinutes,
  parseLocalDate,
  safeTimezone,
  setTimezone,
  todayInTimezone,
} from "./timezone";

describe("local day boundaries", () => {
  it("sends Almaty days with an explicit +05:00 offset", () => {
    expect(localDayStart("2026-11-01", "Asia/Almaty")).toBe("2026-11-01T00:00:00+05:00");
    expect(localDayEnd("2026-11-30", "Asia/Almaty")).toBe("2026-11-30T23:59:59.999999+05:00");
  });

  it("ends the day at microsecond precision so the last second is included (regression)", () => {
    // Before consolidation one screen ended days at 23:59:59 and another at .999Z,
    // so operations stored at 23:59:59.5 local time fell outside the filter.
    const end = localDayEnd("2026-11-30", "Asia/Almaty") as string;
    const lastOperation = Date.parse("2026-11-30T23:59:59.5+05:00");
    expect(Date.parse(end)).toBeGreaterThanOrEqual(lastOperation);
  });

  it("uses the offset valid on that day across a DST change", () => {
    expect(localDayStart("2026-01-15", "Europe/Berlin")).toBe("2026-01-15T00:00:00+01:00");
    expect(localDayStart("2026-07-15", "Europe/Berlin")).toBe("2026-07-15T00:00:00+02:00");
    expect(localDayEnd("2026-03-29", "Europe/Berlin")).toBe("2026-03-29T23:59:59.999999+02:00");
    expect(localDayStart("2026-07-15", "America/New_York")).toBe("2026-07-15T00:00:00-04:00");
  });

  it("rejects impossible dates instead of rolling them over", () => {
    expect(parseLocalDate("2025-02-29")).toBeNull();
    expect(parseLocalDate("2024-02-29")).toEqual({ year: 2024, month: 2, day: 29 });
    expect(localDayStart("2026-13-01", "Asia/Almaty")).toBeNull();
    expect(localDayEnd("not-a-date", "Asia/Almaty")).toBeNull();
  });
});

describe("today and the current month in a zone", () => {
  it("rolls over at local midnight, not UTC midnight", () => {
    const instant = new Date("2026-11-30T19:30:00Z"); // 00:30 on 1 Dec in Almaty
    expect(todayInTimezone("Asia/Almaty", instant)).toBe("2026-12-01");
    expect(todayInTimezone("UTC", instant)).toBe("2026-11-30");
    expect(currentMonth("Asia/Almaty", new Date("2026-12-31T19:00:00Z"))).toBe("2027-01");
  });

  it("falls back to the default zone for an unknown IANA name", () => {
    expect(safeTimezone("Mars/Olympus")).toBe(DEFAULT_TIMEZONE);
    expect(offsetMinutes(new Date("2026-11-01T00:00:00Z"), "Mars/Olympus")).toBe(300);
  });
});

describe("stored zone", () => {
  afterEach(() => window.localStorage.clear());

  it("reads the default, saves a new zone and notifies this tab", () => {
    expect(currentTimezone()).toBe(DEFAULT_TIMEZONE);
    const listener = vi.fn();
    window.addEventListener(TIMEZONE_EVENT, listener);
    setTimezone("Asia/Aqtobe");
    window.removeEventListener(TIMEZONE_EVENT, listener);
    expect(currentTimezone()).toBe("Asia/Aqtobe");
    expect(listener).toHaveBeenCalledTimes(1);
  });
});
