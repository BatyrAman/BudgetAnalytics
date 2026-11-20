import { describe, expect, it } from "vitest";
import type { MonthSummary } from "@/lib/types";
import { cashflowMonths } from "@/components/dashboard-charts";

const months: MonthSummary[] = Array.from({ length: 12 }, (_, i) => ({
  month: `2026-${String(i + 1).padStart(2, "0")}`,
  income: "0.00",
  net_expenses: "0.00",
  net_cash_flow: "0.00",
  savings_rate: null,
  transaction_count: 0,
}));

describe("cashflowMonths", () => {
  it("shows all 12 months of the year on desktop", () => {
    expect(cashflowMonths(months, "2026-11", false)).toHaveLength(12);
  });

  it("shows the last 6 months up to the current month on mobile", () => {
    expect(cashflowMonths(months, "2026-11", true).map((m) => m.month)).toEqual([
      "2026-06",
      "2026-07",
      "2026-08",
      "2026-09",
      "2026-10",
      "2026-11",
    ]);
  });

  it("shows fewer months early in the year on mobile", () => {
    expect(cashflowMonths(months, "2026-02", true).map((m) => m.month)).toEqual([
      "2026-01",
      "2026-02",
    ]);
  });
});
