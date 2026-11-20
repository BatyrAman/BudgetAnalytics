import { describe, expect, it } from "vitest";

import {
  formatDate,
  formatDateTime,
  formatMoney,
  formatMonth,
  formatPercent,
  formatPeriod,
  formatPp,
  parseAmountInput,
  signForType,
} from "./format";

const NBSP = " ";

describe("formatMoney", () => {
  it("groups thousands with a no-break space, uses a decimal comma and the tenge sign", () => {
    expect(formatMoney("1250000.50", "KZT")).toBe(`1${NBSP}250${NBSP}000,50${NBSP}₸`);
  });

  it("keeps exact cents from the decimal string (no float rounding)", () => {
    // 9 999 999 999 999 999.99 cannot be represented exactly as a JS number.
    expect(formatMoney("9999999999999999.99", "KZT")).toBe(
      `9${NBSP}999${NBSP}999${NBSP}999${NBSP}999${NBSP}999,99${NBSP}₸`,
    );
    expect(formatMoney("0.10", "KZT")).toBe(`0,10${NBSP}₸`);
  });

  it("hides zero cents only when asked (metric cards, D-8)", () => {
    expect(formatMoney("1723820.00", "KZT", { hideZeroCents: true })).toBe(
      `1${NBSP}723${NBSP}820${NBSP}₸`,
    );
    expect(formatMoney("1723820.75", "KZT", { hideZeroCents: true })).toBe(
      `1${NBSP}723${NBSP}820,75${NBSP}₸`,
    );
    expect(formatMoney("1723820.00", "KZT")).toBe(`1${NBSP}723${NBSP}820,00${NBSP}₸`);
  });

  it("uses a typographic minus for negative balances", () => {
    expect(formatMoney("-1500.00", "KZT")).toBe(`−1${NBSP}500,00${NBSP}₸`);
  });

  it("applies an explicit sign for transaction types and falls back to the ISO code", () => {
    expect(formatMoney("12500.00", "KZT", { sign: "−" })).toBe(`−12${NBSP}500,00${NBSP}₸`);
    expect(formatMoney("1250.00", "USD", { sign: "+" })).toBe(`+1${NBSP}250,00${NBSP}$`);
    expect(formatMoney("10.00", "GBP")).toBe(`10,00${NBSP}GBP`);
  });
});

describe("signForType", () => {
  it.each([
    ["income", "+"],
    ["refund", "+"],
    ["transfer_in", "+"],
    ["expense", "−"],
    ["transfer_out", "−"],
  ] as const)("%s → %s", (type, sign) => {
    expect(signForType(type)).toBe(sign);
  });
});

describe("percentages", () => {
  it("formats metric and table percentages and null as a dash", () => {
    expect(formatPercent("80.00")).toBe(`80${NBSP}%`);
    expect(formatPercent("118.75", true)).toBe(`118,75${NBSP}%`);
    expect(formatPercent("36.48")).toBe(`36,48${NBSP}%`);
    expect(formatPercent(null)).toBe("—");
  });

  it("never truncates digits returned by the API (EAR has 4 decimals)", () => {
    expect(formatPercent("17.2271")).toBe(`17,2271${NBSP}%`);
    expect(formatPercent("17.2271", true)).toBe(`17,2271${NBSP}%`);
    expect(formatPercent("14.0000")).toBe(`14${NBSP}%`);
    expect(formatMoney("0.005", "KZT")).toBe(`0,005${NBSP}₸`);
  });

  it("formats percentage points with an explicit sign", () => {
    expect(formatPp("3.40")).toBe("+3,4 п. п.");
    expect(formatPp("-2.00")).toBe("−2 п. п.");
    expect(formatPp(null)).toBe("—");
  });
});

describe("dates in Asia/Almaty", () => {
  it("shows UTC instants in the local time zone", () => {
    // 2026-11-17T19:30Z is 18.11.2026 00:30 in Almaty (UTC+5).
    expect(formatDate("2026-11-17T19:30:00Z")).toBe("18.11.2026");
    expect(formatDateTime("2026-11-17T19:30:00Z")).toContain("00:30");
  });

  it("formats months and periods without a year suffix", () => {
    expect(formatMonth("2026-11")).toBe("ноябрь 2026");
    expect(formatPeriod("2026-11-01", "2026-11-30")).toBe("1–30 нояб. 2026");
    expect(formatPeriod("2026-10-28", "2026-11-03")).toBe("28 окт. – 3 нояб. 2026");
    expect(formatPeriod("2025-12-15", "2026-01-10")).toBe("15 дек. 2025 – 10 янв. 2026");
  });
});

describe("parseAmountInput", () => {
  it("accepts comma or dot, strips spaces and limits to 2 decimals", () => {
    expect(parseAmountInput("1 250 000,5")).toBe("1250000.5");
    expect(parseAmountInput("12.345")).toBe("12.34");
    expect(parseAmountInput("abc")).toBe("");
  });
});
