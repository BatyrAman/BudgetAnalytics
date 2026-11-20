import { describe, expect, it } from "vitest";

import {
  daysInMonth,
  isIsoDate,
  localDayBoundary,
  monthOf,
  presetRange,
  todayInTimezone,
  transactionsHref,
  yearOf,
} from "./period";

describe("todayInTimezone", () => {
  it("uses the local date of the time zone, not UTC", () => {
    // 2026-11-30 20:30 UTC is already 1 December in Almaty (UTC+05:00).
    const instant = new Date("2026-11-30T20:30:00Z");
    expect(todayInTimezone("Asia/Almaty", instant)).toBe("2026-12-01");
    expect(todayInTimezone("UTC", instant)).toBe("2026-11-30");
  });

  it("falls back to Asia/Almaty for an unknown zone", () => {
    const instant = new Date("2026-11-30T20:30:00Z");
    expect(todayInTimezone("Not/AZone", instant)).toBe("2026-12-01");
  });
});

describe("presetRange", () => {
  it("returns the whole current month", () => {
    expect(presetRange("month", "2026-11-19")).toEqual({ from: "2026-11-01", to: "2026-11-30" });
    expect(presetRange("month", "2027-01-31")).toEqual({ from: "2027-01-01", to: "2027-01-31" });
  });

  it("crosses the year boundary for the previous month", () => {
    expect(presetRange("previous", "2027-01-05")).toEqual({
      from: "2026-12-01",
      to: "2026-12-31",
    });
    expect(presetRange("previous", "2026-11-19")).toEqual({
      from: "2026-10-01",
      to: "2026-10-31",
    });
  });

  it("handles February in leap and non-leap years", () => {
    expect(presetRange("previous", "2028-03-15")).toEqual({
      from: "2028-02-01",
      to: "2028-02-29",
    });
    expect(presetRange("month", "2027-02-10")).toEqual({ from: "2027-02-01", to: "2027-02-28" });
  });

  it("covers three months including the current one, across a year boundary", () => {
    expect(presetRange("quarter", "2026-11-19")).toEqual({
      from: "2026-09-01",
      to: "2026-11-30",
    });
    expect(presetRange("quarter", "2027-02-01")).toEqual({
      from: "2026-12-01",
      to: "2027-02-28",
    });
    expect(presetRange("quarter", "2027-01-10")).toEqual({
      from: "2026-11-01",
      to: "2027-01-31",
    });
  });

  it("returns the calendar year", () => {
    expect(presetRange("year", "2028-02-29")).toEqual({ from: "2028-01-01", to: "2028-12-31" });
  });
});

describe("helpers", () => {
  it("derives month and year from a date", () => {
    expect(monthOf("2026-12-31")).toBe("2026-12");
    expect(yearOf("2026-12-31")).toBe(2026);
  });

  it("knows month lengths", () => {
    expect(daysInMonth(2028, 2)).toBe(29);
    expect(daysInMonth(2100, 2)).toBe(28);
    expect(daysInMonth(2026, 12)).toBe(31);
  });

  it("validates ISO dates", () => {
    expect(isIsoDate("2028-02-29")).toBe(true);
    expect(isIsoDate("2027-02-29")).toBe(false);
    expect(isIsoDate("2026-13-01")).toBe(false);
    expect(isIsoDate("abc")).toBe(false);
    expect(isIsoDate(null)).toBe(false);
  });

  it("builds local day boundaries with the zone offset", () => {
    expect(localDayBoundary("2026-11-01", "start", "Asia/Almaty")).toBe(
      "2026-11-01T00:00:00+05:00",
    );
    expect(localDayBoundary("2026-11-30", "end", "Asia/Almaty")).toBe(
      "2026-11-30T23:59:59.999999+05:00",
    );
    expect(localDayBoundary("2026-07-01", "start", "Europe/Berlin")).toBe(
      "2026-07-01T00:00:00+02:00",
    );
    expect(localDayBoundary("2026-01-01", "end", "America/New_York")).toBe(
      "2026-01-01T23:59:59.999999-05:00",
    );
  });

  it("builds the transactions link for a category and period", () => {
    const href = transactionsHref(7, { from: "2026-11-01", to: "2026-11-30" }, "Asia/Almaty");
    const url = new URL(href, "http://localhost");
    expect(url.pathname).toBe("/transactions");
    expect(url.searchParams.get("category_id")).toBe("7");
    expect(url.searchParams.get("start_date")).toBe("2026-11-01T00:00:00+05:00");
    expect(url.searchParams.get("end_date")).toBe("2026-11-30T23:59:59.999999+05:00");
  });
});
