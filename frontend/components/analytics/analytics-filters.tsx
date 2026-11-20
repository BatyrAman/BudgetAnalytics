"use client";

import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { useTimezone as useSharedTimezone } from "@/lib/timezone";

import { DEFAULT_TIMEZONE } from "@/lib/api/client";
import { useAccounts, useDefaultCurrency } from "@/lib/api/hooks";
import type { AnalyticsFilters } from "@/lib/api/client";
import { formatPeriod } from "@/lib/format";

import {
  PERIOD_PRESETS,
  isIsoDate,
  presetRange,
  todayInTimezone,
  type DateRange,
  type PeriodPreset,
} from "./period";

/** User's IANA time zone (browser setting, follows Settings); the default zone during SSR. */
export function useTimezone(): string {
  return useSharedTimezone() ?? DEFAULT_TIMEZONE;
}

export type AnalyticsFilterState = {
  preset: PeriodPreset;
  range: DateRange;
  /** Null while the custom range is invalid (no API calls are made). */
  filters: AnalyticsFilters | null;
  rangeError: string | null;
  currency: string;
  currencies: string[];
  timezone: string;
  setPreset: (preset: PeriodPreset) => void;
  setCustomRange: (range: DateRange) => void;
  setCurrency: (currency: string) => void;
};

const PRESET_KEYS = new Set<string>(PERIOD_PRESETS.map(([key]) => key));

export function parsePreset(value: string | null): PeriodPreset | null {
  return value && PRESET_KEYS.has(value) ? (value as PeriodPreset) : null;
}

/**
 * Period + currency state shared by AN-1 and AN-2. Preset ranges are derived
 * from today's date in the user's time zone; nothing is hardcoded.
 */
export function useAnalyticsFilterState(initial?: {
  preset?: PeriodPreset | null;
  custom?: DateRange | null;
  currency?: string | null;
}): AnalyticsFilterState {
  const timezone = useTimezone();
  const today = todayInTimezone(timezone);
  const defaultCurrency = useDefaultCurrency();
  const { data: accounts } = useAccounts(true);

  const [preset, setPresetState] = useState<PeriodPreset>(
    initial?.preset === "custom" && !initial.custom ? "month" : (initial?.preset ?? "month"),
  );
  const [custom, setCustom] = useState<DateRange>(initial?.custom ?? presetRange("month", today));
  const [selectedCurrency, setCurrency] = useState<string | null>(initial?.currency ?? null);

  const range = preset === "custom" ? custom : presetRange(preset, today);
  const currency = selectedCurrency ?? defaultCurrency;

  const currencies = useMemo(() => {
    const codes = new Set<string>([defaultCurrency]);
    for (const account of accounts ?? []) codes.add(account.currency_code);
    codes.add(currency);
    return [...codes].sort();
  }, [accounts, defaultCurrency, currency]);

  let rangeError: string | null = null;
  if (!isIsoDate(range.from) || !isIsoDate(range.to)) {
    rangeError = "Укажите даты начала и окончания периода.";
  } else if (range.from > range.to) {
    rangeError = "Дата начала не может быть позже даты окончания.";
  }

  const filters = useMemo<AnalyticsFilters | null>(
    () => (rangeError ? null : { date_from: range.from, date_to: range.to, currency }),
    [rangeError, range.from, range.to, currency],
  );

  return {
    preset,
    range,
    filters,
    rangeError,
    currency,
    currencies,
    timezone,
    setPreset: (next) => {
      if (next === "custom") setCustom(range);
      setPresetState(next);
    },
    setCustomRange: setCustom,
    setCurrency,
  };
}

/** Filter state initialised from `?preset=&from=&to=&currency=` (links between AN-1 and AN-2). */
export function useAnalyticsFilterStateFromUrl(): AnalyticsFilterState {
  const params = useSearchParams();
  const from = params.get("from");
  const to = params.get("to");
  return useAnalyticsFilterState({
    preset: parsePreset(params.get("preset")),
    custom: isIsoDate(from) && isIsoDate(to) ? { from, to } : null,
    currency: params.get("currency"),
  });
}

/** Query string that reopens the same filters on another analytics screen. */
export function filtersQuery(state: AnalyticsFilterState): string {
  const params = new URLSearchParams({ preset: state.preset, currency: state.currency });
  if (state.preset === "custom") {
    params.set("from", state.range.from);
    params.set("to", state.range.to);
  }
  return params.toString();
}

export function AnalyticsFiltersPanel({ state }: { state: AnalyticsFilterState }) {
  const { preset, range, currency, currencies, timezone, rangeError } = state;
  return (
    <section className="analytics-filters card-surface" aria-label="Фильтры аналитики">
      <div className="analytics-filter-top">
        <div className="segmented-control" role="group" aria-label="Период">
          {PERIOD_PRESETS.map(([key, label]) => (
            <button
              type="button"
              key={key}
              className={preset === key ? "selected" : ""}
              aria-pressed={preset === key}
              onClick={() => state.setPreset(key)}
            >
              {label}
            </button>
          ))}
        </div>
        <label className="analytics-currency">
          <span className="sr-only">Валюта</span>
          <select value={currency} onChange={(event) => state.setCurrency(event.target.value)}>
            {currencies.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </label>
      </div>
      {preset === "custom" && (
        <div className="date-range-fields">
          <label>
            С{" "}
            <input
              type="date"
              value={range.from}
              max={range.to}
              aria-invalid={rangeError ? true : undefined}
              onChange={(event) => state.setCustomRange({ from: event.target.value, to: range.to })}
            />
          </label>
          <label>
            По{" "}
            <input
              type="date"
              value={range.to}
              min={range.from}
              aria-invalid={rangeError ? true : undefined}
              onChange={(event) =>
                state.setCustomRange({ from: range.from, to: event.target.value })
              }
            />
          </label>
        </div>
      )}
      {rangeError && (
        <p className="form-error" role="alert">
          {rangeError}
        </p>
      )}
      <div className="analytics-period-line">
        <span>{rangeError ? "—" : formatPeriod(range.from, range.to)}</span>
        <span>Часовой пояс: {timezone}</span>
      </div>
    </section>
  );
}
