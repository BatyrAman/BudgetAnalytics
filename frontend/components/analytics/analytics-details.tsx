"use client";

import Link from "next/link";
import { useState } from "react";

import { AppShell } from "@/components/app-shell";
import { EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/common";
import type { AnalyticsFilters } from "@/lib/api/client";
import { useCategories, useCategoryBreakdown, useSavingsRate } from "@/lib/api/hooks";
import { formatMoney, formatPercent } from "@/lib/format";

import { CategoryDonut } from "./analytics-charts";
import {
  AnalyticsFiltersPanel,
  filtersQuery,
  useAnalyticsFilterStateFromUrl,
} from "./analytics-filters";
import { NullableValue } from "./analytics-overview";
import { CategoryIcon } from "./category-icon";
import { transactionsHref, type DateRange } from "./period";

type Kind = "expense" | "income";

function BreakdownSection({
  kind,
  filters,
  range,
  timezone,
}: {
  kind: Kind;
  filters: AnalyticsFilters;
  range: DateRange;
  timezone: string;
}) {
  const { data, error, mutate } = useCategoryBreakdown(kind, filters);
  const { data: categories } = useCategories();
  const title = kind === "expense" ? "расходов" : "доходов";
  if (error) return <ErrorState error={error} retry={() => void mutate()} />;
  if (!data) {
    return (
      <div className="analytics-breakdown-grid" aria-busy="true">
        <div className="chart-card card-surface">
          <Skeleton className="large" />
        </div>
        <div className="card-surface">
          <Skeleton className="medium" />
          <Skeleton className="medium" />
        </div>
      </div>
    );
  }
  if (data.items.length === 0) {
    return (
      <EmptyState
        title={`Нет ${title} за период`}
        description="Выберите другой период или валюту"
      />
    );
  }
  const currency = data.currency_code;
  return (
    <section className="analytics-breakdown-grid" id={`analytics-panel-${kind}`} role="tabpanel">
      <div className="chart-card card-surface">
        <h2>Категории {title}</h2>
        <CategoryDonut data={data} />
      </div>
      <section className="entity-section card-surface analytics-category-table">
        <header>
          <h2>Категории</h2>
        </header>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Категория</th>
                <th scope="col">Сумма</th>
                <th scope="col">Доля</th>
                <th scope="col">Операций</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((item) => {
                const category = categories?.find((row) => row.id === item.category_id);
                return (
                  <tr key={item.category_id}>
                    <td>
                      <Link
                        className="category-row-link"
                        href={transactionsHref(item.category_id, range, timezone)}
                      >
                        <span
                          className="analytics-category-icon"
                          style={category ? { color: category.color } : undefined}
                        >
                          <CategoryIcon name={category?.icon} />
                        </span>
                        {item.name}
                      </Link>
                    </td>
                    <td>{formatMoney(item.amount, currency, { hideZeroCents: true })}</td>
                    <td>
                      <NullableValue
                        value={
                          item.share_percent === null
                            ? null
                            : formatPercent(item.share_percent, true)
                        }
                        reason="Итог за период равен нулю — доля не считается"
                      />
                    </td>
                    <td>{item.transaction_count}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}

function SavingsRateSection({ filters }: { filters: AnalyticsFilters }) {
  const { data, error, mutate } = useSavingsRate(filters);
  if (error) return <ErrorState error={error} retry={() => void mutate()} />;
  if (!data) {
    return (
      <section className="analytics-rate-grid" aria-busy="true">
        <div className="analytics-metric card-surface">
          <Skeleton className="large" />
        </div>
        <div className="analytics-metric card-surface">
          <Skeleton className="large" />
        </div>
      </section>
    );
  }
  const noIncome = "Нет доходов за период — показатель не рассчитывается";
  return (
    <section className="analytics-rate-grid">
      <article className="analytics-metric card-surface">
        <span>Норма сбережений</span>
        <strong className="tabular-nums">
          <NullableValue
            value={data.savings_rate === null ? null : formatPercent(data.savings_rate, true)}
            reason={noIncome}
          />
        </strong>
      </article>
      <article className="analytics-metric card-surface">
        <span>Расходы к доходам</span>
        <strong className="tabular-nums">
          <NullableValue
            value={
              data.expense_to_income_percent === null
                ? null
                : formatPercent(data.expense_to_income_percent, true)
            }
            reason={noIncome}
          />
        </strong>
      </article>
    </section>
  );
}

export function AnalyticsDetails() {
  const state = useAnalyticsFilterStateFromUrl();
  const [kind, setKind] = useState<Kind>("expense");
  const { filters, range, timezone } = state;
  return (
    <div className="entity-page analytics-page">
      <Link href={`/analytics?${filtersQuery(state)}`} className="back-link">
        ← К аналитике
      </Link>
      <PageHeader title="Детальная аналитика" description="Категории, норма сбережений" />
      <AnalyticsFiltersPanel state={state} />
      <div className="segmented-control analytics-tabs" role="tablist" aria-label="Тип категорий">
        {(
          [
            ["expense", "Расходы"],
            ["income", "Доходы"],
          ] as const
        ).map(([value, label]) => (
          <button
            type="button"
            key={value}
            role="tab"
            aria-selected={kind === value}
            aria-controls={`analytics-panel-${value}`}
            className={kind === value ? "selected" : ""}
            onClick={() => setKind(value)}
          >
            {label}
          </button>
        ))}
      </div>
      {filters && (
        <>
          <BreakdownSection kind={kind} filters={filters} range={range} timezone={timezone} />
          <SavingsRateSection filters={filters} />
        </>
      )}
      <aside className="backend-note">
        <strong>Требует backend</strong>
        <p>
          Разбивка по неделям и дням, по счетам и банкам, тренды категорий во времени появятся после
          доработки backend
        </p>
      </aside>
    </div>
  );
}

export function AnalyticsDetailsScreen() {
  return (
    <AppShell>
      <AnalyticsDetails />
    </AppShell>
  );
}
