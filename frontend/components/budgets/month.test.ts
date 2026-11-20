import { describe, expect, it } from "vitest";

import { currentMonth, monthBounds, monthLabel, recentMonths, shiftMonth } from "./month";

describe("month helpers", () => {
  it("takes the current month in the user's time zone", () => {
    // 2026-11-30 20:30 UTC is already 1 December in Almaty (UTC+5).
    const instant = new Date("2026-11-30T20:30:00Z");
    expect(currentMonth("Asia/Almaty", instant)).toBe("2026-12");
    expect(currentMonth("UTC", instant)).toBe("2026-11");
  });

  it("shifts across year boundaries", () => {
    expect(shiftMonth("2026-01", -1)).toBe("2025-12");
    expect(shiftMonth("2026-12", 1)).toBe("2027-01");
    expect(recentMonths("2026-02", 3)).toEqual(["2025-12", "2026-01", "2026-02"]);
  });

  it("builds inclusive month bounds with the zone offset", () => {
    const february = monthBounds("2026-02", "Asia/Almaty");
    expect(february).toEqual({
      start: "2026-02-01T00:00:00+05:00",
      end: "2026-02-28T23:59:59.999999+05:00",
    });
    // Same instant as UTC midnight minus the +05:00 offset.
    expect(Date.parse(february.start)).toBe(Date.parse("2026-01-31T19:00:00Z"));
    // Leap year, UTC.
    expect(monthBounds("2028-02", "UTC").end).toBe("2028-02-29T23:59:59.999999+00:00");
    // DST zone: March starts in winter time, ends in summer time.
    expect(monthBounds("2026-03", "Europe/Berlin")).toEqual({
      start: "2026-03-01T00:00:00+01:00",
      end: "2026-03-31T23:59:59.999999+02:00",
    });
  });

  it("labels months in Russian", () => {
    expect(monthLabel("2026-11")).toBe("Ноябрь 2026");
  });
});
