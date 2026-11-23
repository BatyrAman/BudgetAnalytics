import { describe, expect, it } from "vitest";

import {
  DATE_INVALID,
  DATE_TOO_EARLY,
  DATE_TOO_LATE,
  END_NOT_AFTER_START,
  TERM_RULES,
  TERM_TOO_LONG,
  addMonthsIso,
  dateBoundError,
  dateRangeError,
  depositFieldErrors,
  termMonthsError,
  termTooLong,
} from "./deposit-utils";

describe("termMonthsError", () => {
  it.each([
    ["1", null],
    ["600", null],
    ["601", "Срок — целое число месяцев от 1 до 600."],
    ["0", "Срок — целое число месяцев от 1 до 600."],
    ["1000", "Срок — целое число месяцев от 1 до 600."],
    ["12.5", "Срок — целое число месяцев от 1 до 600."],
    ["", "Укажите срок в месяцах."],
  ])("%s → %s", (value, expected) => {
    expect(termMonthsError(value)).toBe(expected);
  });
});

describe("addMonthsIso (mirrors backend add_months)", () => {
  it.each([
    ["2025-01-31", 1, "2025-02-28"],
    ["2024-01-31", 1, "2024-02-29"], // leap year
    ["2025-01-31", 2, "2025-03-31"], // from the start, not chained
    ["2025-11-30", 3, "2026-02-28"],
    ["2024-02-29", 12, "2025-02-28"],
    ["2024-02-29", 600, "2074-02-28"],
    ["2000-02-29", 1200, "2100-02-28"], // 2100 is not a leap year
    ["1900-01-01", 600, "1950-01-01"],
    ["2200-12-31", 600, "2250-12-31"],
    ["2025-05-15", 0, "2025-05-15"],
  ])("%s + %i months = %s", (start, months, expected) => {
    expect(addMonthsIso(start, months)).toBe(expected);
  });

  it("rejects a non-ISO value", () => {
    expect(() => addMonthsIso("19.11.2026", 1)).toThrow();
  });
});

describe("dateBoundError", () => {
  it.each([
    ["1900-01-01", null],
    ["2200-12-31", null],
    ["2026-11-19", null],
    ["1899-12-31", DATE_TOO_EARLY],
    ["0001-01-01", DATE_TOO_EARLY],
    ["2201-01-01", DATE_TOO_LATE],
    ["9999-12-31", DATE_TOO_LATE],
    ["275760-09-13", DATE_INVALID], // 6-digit year a browser may produce
    ["", DATE_INVALID],
  ])("%s → %s", (value, expected) => {
    expect(dateBoundError(value)).toBe(expected);
  });
});

describe("termTooLong / dateRangeError", () => {
  it.each([
    ["2025-01-01", "2075-01-01", false], // exactly 600 months
    ["2025-01-01", "2075-01-02", true], // 600 months + 1 day
    ["2024-02-29", "2074-02-28", false], // leap start, clamped
    ["2024-02-29", "2074-03-01", true],
    ["2025-01-31", "2075-01-31", false],
  ])("%s → %s too long: %s", (start, end, expected) => {
    expect(termTooLong(start, end)).toBe(expected);
  });

  it("checks presence, bounds, order and the 600-month maximum", () => {
    expect(dateRangeError("2025-01-01", "2075-01-01")).toEqual({});
    expect(dateRangeError("2025-01-01", "2075-01-02")).toEqual({ end: TERM_TOO_LONG });
    expect(dateRangeError("2025-01-01", "2025-01-01")).toEqual({ end: END_NOT_AFTER_START });
    expect(dateRangeError("1899-12-31", "1900-02-01")).toEqual({ start: DATE_TOO_EARLY });
    expect(dateRangeError("2200-01-01", "2201-01-01")).toEqual({ end: DATE_TOO_LATE });
    expect(dateRangeError("", "")).toEqual({
      start: "Укажите дату начала.",
      end: "Укажите дату окончания.",
    });
  });
});

describe("depositFieldErrors", () => {
  it("puts a field-less issue on the term field and refines date bounds", () => {
    expect(
      depositFieldErrors(
        [
          { field: "_", message: "Некорректное значение.", type: "value_error" },
          { field: "start_date", message: "x", type: "greater_than_equal" },
          { field: "end_date", message: "x", type: "less_than_equal" },
          { field: "principal", message: "Значение слишком большое.", type: "less_than_equal" },
          { field: "end_date", message: "Обязательное поле.", type: "missing" },
        ],
        "term_months",
      ),
    ).toEqual([
      { field: "term_months", message: TERM_RULES },
      { field: "start_date", message: DATE_TOO_EARLY },
      { field: "end_date", message: DATE_TOO_LATE },
      // Unrelated fields and issue types keep the generic mapping.
      { field: "principal", message: "Значение слишком большое." },
      { field: "end_date", message: "Обязательное поле." },
    ]);
  });
});
