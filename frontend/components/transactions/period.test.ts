import { describe, expect, it } from "vitest";

import {
  fromLocalDateTimeInput,
  localDayEnd,
  localDayStart,
  matchingPreset,
  presetRange,
  toLocalDateInput,
  toLocalDateTimeInput,
} from "./period";

const ALMATY = "Asia/Almaty"; // UTC+5, no DST

describe("local day boundaries", () => {
  it("adds the zone offset to local day start and inclusive end", () => {
    expect(localDayStart("2026-11-01", ALMATY)).toBe("2026-11-01T00:00:00+05:00");
    expect(localDayEnd("2026-11-30", ALMATY)).toBe("2026-11-30T23:59:59.999999+05:00");
  });

  it("local midnight in Almaty is 19:00 UTC of the previous day", () => {
    const start = localDayStart("2026-11-01", ALMATY)!;
    expect(new Date(start).toISOString()).toBe("2026-10-31T19:00:00.000Z");
  });

  it("works for other zones, including negative offsets and DST", () => {
    expect(localDayStart("2026-01-15", "UTC")).toBe("2026-01-15T00:00:00+00:00");
    expect(localDayEnd("2026-01-15", "America/New_York")).toBe("2026-01-15T23:59:59.999999-05:00");
    expect(localDayStart("2026-07-15", "America/New_York")).toBe("2026-07-15T00:00:00-04:00");
  });

  it("rejects invalid dates", () => {
    expect(localDayStart("2026-02-30", ALMATY)).toBeNull();
    expect(localDayEnd("not-a-date", ALMATY)).toBeNull();
    expect(localDayStart("", ALMATY)).toBeNull();
  });

  it("handles leap day", () => {
    expect(localDayEnd("2028-02-29", ALMATY)).toBe("2028-02-29T23:59:59.999999+05:00");
  });
});

describe("presets", () => {
  // 2026-11-30 20:30 UTC is already 1 December 01:30 in Almaty.
  const lateUtc = new Date("2026-11-30T20:30:00Z");

  it("uses the calendar month of the user's time zone, not UTC", () => {
    expect(presetRange("this_month", lateUtc, ALMATY)).toEqual({
      start_date: "2026-12-01T00:00:00+05:00",
      end_date: "2026-12-31T23:59:59.999999+05:00",
    });
  });

  it("last month crosses the year boundary", () => {
    expect(presetRange("last_month", new Date("2026-01-10T06:00:00Z"), ALMATY)).toEqual({
      start_date: "2025-12-01T00:00:00+05:00",
      end_date: "2025-12-31T23:59:59.999999+05:00",
    });
  });

  it("three months include the current month and the two before it", () => {
    expect(presetRange("three_months", new Date("2026-02-15T06:00:00Z"), ALMATY)).toEqual({
      start_date: "2025-12-01T00:00:00+05:00",
      end_date: "2026-02-28T23:59:59.999999+05:00",
    });
  });

  it("year is 1 January … 31 December", () => {
    expect(presetRange("year", new Date("2026-06-15T06:00:00Z"), ALMATY)).toEqual({
      start_date: "2026-01-01T00:00:00+05:00",
      end_date: "2026-12-31T23:59:59.999999+05:00",
    });
  });

  it("recognises the active preset", () => {
    const now = new Date("2026-11-19T06:00:00Z");
    expect(matchingPreset(presetRange("last_month", now, ALMATY), now, ALMATY)).toBe("last_month");
    expect(
      matchingPreset({ start_date: "2026-11-02T00:00:00+05:00", end_date: "x" }, now, ALMATY),
    ).toBeNull();
  });
});

describe("conversions for inputs", () => {
  it("shows an instant as the local date of the zone", () => {
    expect(toLocalDateInput("2026-10-31T19:00:00Z", ALMATY)).toBe("2026-11-01");
    expect(toLocalDateInput("2026-11-01T00:00:00+06:00", ALMATY)).toBe("2026-10-31");
    expect(toLocalDateInput("garbage", ALMATY)).toBe("");
  });

  it("round-trips datetime-local values with the zone offset", () => {
    expect(fromLocalDateTimeInput("2026-11-19T10:15", ALMATY)).toBe("2026-11-19T10:15:00+05:00");
    expect(toLocalDateTimeInput("2026-11-19T05:15:00Z", ALMATY)).toBe("2026-11-19T10:15");
    expect(fromLocalDateTimeInput("2026-11-19T25:00", ALMATY)).toBeNull();
    expect(fromLocalDateTimeInput("", ALMATY)).toBeNull();
  });
});
