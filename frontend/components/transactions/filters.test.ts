import { describe, expect, it } from "vitest";

import {
  buildListQuery,
  categoriesForType,
  compareDecimal,
  isAmountRangeInvalid,
  parseListQuery,
} from "./filters";
import { categories } from "./test-utils";

describe("URL query <-> filters", () => {
  it("parses links from Analytics/Budgets and ignores invalid values", () => {
    const { filters, page } = parseListQuery(
      new URLSearchParams(
        "category_id=3&start_date=2026-11-01T00:00:00%2B05:00&end_date=2026-11-30&transaction_type=bogus&limit=50&offset=50&min_amount=1e5&currency=kzt",
      ),
      "Asia/Almaty",
    );
    expect(filters).toEqual({
      category_id: 3,
      start_date: "2026-11-01T00:00:00+05:00",
      end_date: "2026-11-30T23:59:59.999999+05:00",
    });
    expect(page).toEqual({ limit: 50, offset: 50 });
  });

  it("falls back to 20 rows for unsupported page sizes", () => {
    expect(parseListQuery(new URLSearchParams("limit=500"), "UTC").page).toEqual({
      limit: 20,
      offset: 0,
    });
  });

  it("serializes with defaults omitted and round-trips", () => {
    const query = buildListQuery(
      { search: "кофе", category_id: 3, start_date: "2026-11-01T00:00:00+05:00" },
      { limit: 20, offset: 0 },
    );
    expect(query).toBe(
      "start_date=2026-11-01T00%3A00%3A00%2B05%3A00&category_id=3&search=%D0%BA%D0%BE%D1%84%D0%B5",
    );
    expect(parseListQuery(new URLSearchParams(query), "Asia/Almaty").filters).toEqual({
      start_date: "2026-11-01T00:00:00+05:00",
      category_id: 3,
      search: "кофе",
    });
  });
});

describe("helpers", () => {
  it("compares decimal strings without floats", () => {
    expect(compareDecimal("10", "9.99")).toBe(1);
    expect(compareDecimal("0010.5", "10.50")).toBe(0);
    expect(compareDecimal("12345678901234567.01", "12345678901234567.02")).toBe(-1);
    expect(isAmountRangeInvalid("100", "50")).toBe(true);
    expect(isAmountRangeInvalid("50", undefined)).toBe(false);
  });

  it("filters categories by transaction type", () => {
    expect(categoriesForType(categories, "income").map((c) => c.id)).toEqual([2, 3]);
    expect(categoriesForType(categories, "refund").map((c) => c.id)).toEqual([1, 3]);
    expect(categoriesForType(categories, "transfer_out").map((c) => c.id)).toEqual([1, 2, 3]);
  });
});
