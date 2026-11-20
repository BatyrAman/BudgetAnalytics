"use client";

import { useEffect, useEffectEvent, useState } from "react";
import { Filter, Search, X } from "lucide-react";

import { formatMoney, parseAmountInput } from "@/lib/format";
import type { Account, Bank, Category } from "@/lib/types";

import {
  CURRENCY_CHOICES,
  TRANSACTION_TYPES,
  TYPE_LABELS,
  isAmountRangeInvalid,
  type ListFilters,
} from "./filters";
import {
  PERIOD_PRESETS,
  localDayEnd,
  localDayStart,
  matchingPreset,
  presetRange,
  toLocalDateInput,
} from "./period";

export type FilterOptions = {
  categories: Category[];
  accounts: Account[];
  banks: Bank[];
};

type PanelProps = {
  filters: ListFilters;
  options: FilterOptions;
  timeZone: string;
  now: Date;
  activeCount: number;
  onChange: (patch: Partial<ListFilters>) => void;
  onReset: () => void;
};

/** Text input that commits its value after the user stops typing. */
function useDebouncedValue(value: string, onCommit: (value: string) => void, delay = 400) {
  const [local, setLocal] = useState(value);
  const [seen, setSeen] = useState(value);
  const [committed, setCommitted] = useState(value);
  if (value !== seen) {
    // External change (reset, link, back/forward) — adopt it unless it is our own commit.
    setSeen(value);
    if (value !== committed) {
      setLocal(value);
      setCommitted(value);
    }
  }
  const commit = useEffectEvent((next: string) => {
    setCommitted(next);
    onCommit(next);
  });
  useEffect(() => {
    if (local === committed) return;
    const timer = setTimeout(() => commit(local), delay);
    return () => clearTimeout(timer);
  }, [local, committed, delay]);
  return [local, setLocal] as const;
}

function SearchField({
  value,
  onCommit,
  mobile,
}: {
  value: string;
  onCommit: (v: string) => void;
  mobile?: boolean;
}) {
  const [local, setLocal] = useDebouncedValue(value, onCommit);
  if (mobile) {
    return (
      <label className="field-label">
        Поиск по описанию
        <input value={local} maxLength={100} onChange={(event) => setLocal(event.target.value)} />
      </label>
    );
  }
  return (
    <label className="search-field">
      <Search aria-hidden="true" />
      <input
        aria-label="Поиск по описанию"
        placeholder="Поиск по описанию"
        maxLength={100}
        value={local}
        onChange={(event) => setLocal(event.target.value)}
      />
    </label>
  );
}

function AmountField({
  label,
  value,
  invalid,
  onCommit,
}: {
  label: string;
  value: string;
  invalid: boolean;
  onCommit: (v: string) => void;
}) {
  const [local, setLocal] = useDebouncedValue(value, onCommit, 600);
  return (
    <label className="field-label">
      {label}
      <input
        inputMode="decimal"
        value={local}
        aria-invalid={invalid || undefined}
        onChange={(event) => setLocal(parseAmountInput(event.target.value))}
      />
    </label>
  );
}

function PeriodFields({
  filters,
  timeZone,
  now,
  onChange,
}: Pick<PanelProps, "filters" | "timeZone" | "now" | "onChange">) {
  const active = matchingPreset(filters, now, timeZone);
  return (
    <>
      <label className="field-label">
        Дата с
        <input
          type="date"
          value={filters.start_date ? toLocalDateInput(filters.start_date, timeZone) : ""}
          onChange={(event) =>
            onChange({ start_date: localDayStart(event.target.value, timeZone) ?? undefined })
          }
        />
      </label>
      <label className="field-label">
        Дата по
        <input
          type="date"
          value={filters.end_date ? toLocalDateInput(filters.end_date, timeZone) : ""}
          onChange={(event) =>
            onChange({ end_date: localDayEnd(event.target.value, timeZone) ?? undefined })
          }
        />
      </label>
      <div className="filter-presets" role="group" aria-label="Быстрый выбор периода">
        {PERIOD_PRESETS.map((preset) => (
          <button
            type="button"
            className="button ghost small"
            key={preset.id}
            aria-pressed={active === preset.id}
            onClick={() => onChange(presetRange(preset.id, now, timeZone))}
          >
            {preset.label}
          </button>
        ))}
      </div>
    </>
  );
}

function MainSelects({
  filters,
  options,
  onChange,
}: Pick<PanelProps, "filters" | "options" | "onChange">) {
  return (
    <>
      <label className="field-label">
        Тип
        <select
          value={filters.transaction_type ?? ""}
          onChange={(event) => {
            const value = event.target.value;
            onChange({
              transaction_type: TRANSACTION_TYPES.find((type) => type === value),
            });
          }}
        >
          <option value="">Все типы</option>
          {TRANSACTION_TYPES.map((type) => (
            <option key={type} value={type}>
              {TYPE_LABELS[type]}
            </option>
          ))}
        </select>
      </label>
      <label className="field-label">
        Категория
        <select
          value={filters.category_id ?? ""}
          onChange={(event) => onChange({ category_id: Number(event.target.value) || undefined })}
        >
          <option value="">Все категории</option>
          {options.categories.map((category) => (
            <option value={category.id} key={category.id}>
              {category.name}
            </option>
          ))}
        </select>
      </label>
      <label className="field-label">
        Счёт
        <select
          value={filters.account_id ?? ""}
          onChange={(event) => onChange({ account_id: Number(event.target.value) || undefined })}
        >
          <option value="">Все счета</option>
          {options.accounts.map((account) => (
            <option value={account.id} key={account.id}>
              {account.name}
              {account.is_archived ? " (архив)" : ""}
            </option>
          ))}
        </select>
      </label>
    </>
  );
}

function ExtraFields({
  filters,
  options,
  onChange,
}: Pick<PanelProps, "filters" | "options" | "onChange">) {
  const invalidRange = isAmountRangeInvalid(filters.min_amount, filters.max_amount);
  const currencies = Array.from(
    new Set([...CURRENCY_CHOICES, ...options.accounts.map((account) => account.currency_code)]),
  );
  return (
    <>
      <label className="field-label">
        Банк
        <select
          value={filters.bank_id ?? ""}
          onChange={(event) => onChange({ bank_id: Number(event.target.value) || undefined })}
        >
          <option value="">Все банки</option>
          {options.banks.map((bank) => (
            <option value={bank.id} key={bank.id}>
              {bank.name}
            </option>
          ))}
        </select>
      </label>
      <label className="field-label">
        Валюта
        <select
          value={filters.currency ?? ""}
          onChange={(event) => onChange({ currency: event.target.value || undefined })}
        >
          <option value="">Все валюты</option>
          {currencies.map((code) => (
            <option key={code} value={code}>
              {code}
            </option>
          ))}
        </select>
      </label>
      <AmountField
        label="Сумма от"
        value={filters.min_amount ?? ""}
        invalid={invalidRange}
        onCommit={(value) => onChange({ min_amount: value || undefined })}
      />
      <AmountField
        label="Сумма до"
        value={filters.max_amount ?? ""}
        invalid={invalidRange}
        onCommit={(value) => onChange({ max_amount: value || undefined })}
      />
    </>
  );
}

/** Human-readable chips for active filters; each chip removes its filter. */
function FilterChips({
  filters,
  options,
  timeZone,
  onChange,
}: Omit<PanelProps, "now" | "activeCount" | "onReset">) {
  const chips: { key: string; label: string; clear: Partial<ListFilters> }[] = [];
  if (filters.start_date || filters.end_date) {
    const from = filters.start_date ? toLocalDateInput(filters.start_date, timeZone) : "…";
    const to = filters.end_date ? toLocalDateInput(filters.end_date, timeZone) : "…";
    chips.push({
      key: "period",
      label: `Период: ${from} — ${to}`,
      clear: { start_date: undefined, end_date: undefined },
    });
  }
  if (filters.transaction_type)
    chips.push({
      key: "type",
      label: TYPE_LABELS[filters.transaction_type],
      clear: { transaction_type: undefined },
    });
  if (filters.category_id)
    chips.push({
      key: "category",
      label: options.categories.find((c) => c.id === filters.category_id)?.name ?? "Категория",
      clear: { category_id: undefined },
    });
  if (filters.account_id)
    chips.push({
      key: "account",
      label: options.accounts.find((a) => a.id === filters.account_id)?.name ?? "Счёт",
      clear: { account_id: undefined },
    });
  if (filters.bank_id)
    chips.push({
      key: "bank",
      label: options.banks.find((b) => b.id === filters.bank_id)?.name ?? "Банк",
      clear: { bank_id: undefined },
    });
  if (filters.currency)
    chips.push({ key: "currency", label: filters.currency, clear: { currency: undefined } });
  if (filters.min_amount)
    chips.push({
      key: "min",
      label: `от ${formatMoney(filters.min_amount, filters.currency ?? "", { hideZeroCents: true }).trim()}`,
      clear: { min_amount: undefined },
    });
  if (filters.max_amount)
    chips.push({
      key: "max",
      label: `до ${formatMoney(filters.max_amount, filters.currency ?? "", { hideZeroCents: true }).trim()}`,
      clear: { max_amount: undefined },
    });
  if (filters.search)
    chips.push({ key: "search", label: `«${filters.search}»`, clear: { search: undefined } });
  if (chips.length === 0) return null;
  return (
    <div className="filter-chips">
      {chips.map((chip) => (
        <button
          type="button"
          key={chip.key}
          aria-label={`Убрать фильтр: ${chip.label}`}
          onClick={() => onChange(chip.clear)}
        >
          {chip.label} <X aria-hidden="true" />
        </button>
      ))}
    </div>
  );
}

/** Desktop/tablet filter panel plus the mobile bottom sheet. */
export function TransactionsFilters(props: PanelProps) {
  const { filters, options, timeZone, now, activeCount, onChange, onReset } = props;
  const [showMore, setShowMore] = useState(
    Boolean(filters.bank_id || filters.currency || filters.min_amount || filters.max_amount),
  );
  const [mobileOpen, setMobileOpen] = useState(false);
  const commitSearch = (value: string) => onChange({ search: value.trim() || undefined });

  return (
    <section className="transaction-filters card-surface" aria-label="Фильтры операций">
      <div className="filter-main">
        <PeriodFields filters={filters} timeZone={timeZone} now={now} onChange={onChange} />
        <MainSelects filters={filters} options={options} onChange={onChange} />
        <SearchField value={filters.search ?? ""} onCommit={commitSearch} />
      </div>
      <div className="filter-actions">
        <button
          type="button"
          className="button secondary small mobile-filter-button"
          onClick={() => setMobileOpen(true)}
        >
          <Filter aria-hidden="true" />
          Фильтры ({activeCount})
        </button>
        <button
          type="button"
          className="button ghost small"
          aria-expanded={showMore}
          onClick={() => setShowMore((open) => !open)}
        >
          Ещё фильтры
        </button>
        {activeCount > 0 && (
          <button type="button" className="text-link" onClick={onReset}>
            Сбросить всё
          </button>
        )}
      </div>
      {showMore && (
        <div className="additional-filters">
          <ExtraFields filters={filters} options={options} onChange={onChange} />
        </div>
      )}
      <FilterChips filters={filters} options={options} timeZone={timeZone} onChange={onChange} />
      {mobileOpen && (
        <div
          className="sheet-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setMobileOpen(false);
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape") setMobileOpen(false);
          }}
        >
          <section
            className="mobile-filter-sheet"
            role="dialog"
            aria-modal="true"
            aria-labelledby="mobile-filter-title"
          >
            <header className="overlay-heading">
              <h2 id="mobile-filter-title">Фильтры</h2>
              <button
                type="button"
                className="icon-button"
                aria-label="Закрыть"
                onClick={() => setMobileOpen(false)}
              >
                <X />
              </button>
            </header>
            <PeriodFields filters={filters} timeZone={timeZone} now={now} onChange={onChange} />
            <MainSelects filters={filters} options={options} onChange={onChange} />
            <ExtraFields filters={filters} options={options} onChange={onChange} />
            <SearchField value={filters.search ?? ""} onCommit={commitSearch} mobile />
            <div className="dialog-actions">
              <button type="button" className="button secondary" onClick={onReset}>
                Сбросить всё
              </button>
              <button type="button" className="button primary" onClick={() => setMobileOpen(false)}>
                Показать операции
              </button>
            </div>
          </section>
        </div>
      )}
    </section>
  );
}
