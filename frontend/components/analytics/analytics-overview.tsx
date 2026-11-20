"use client";

import Link from "next/link";
import { CircleHelp } from "lucide-react";
import { useState } from "react";

import { AppShell } from "@/components/app-shell";
import { EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/common";
import type { AnalyticsFilters } from "@/lib/api/client";
import { useComparison, useMonthly, useSummary } from "@/lib/api/hooks";
import { formatMoney, formatMonth, formatPercent, formatPp } from "@/lib/format";
import type { MetricChange } from "@/lib/types";

import { MonthlyChart, MonthlyTable } from "./analytics-charts";
import {
  AnalyticsFiltersPanel,
  filtersQuery,
  useAnalyticsFilterStateFromUrl,
} from "./analytics-filters";
import { monthOf, yearOf } from "./period";

/** A value that may be `null` in the API: shows «—» with an explanation. */
export function NullableValue({ value, reason }: { value: string | null; reason: string }) {
  if (value !== null) return <>{value}</>;
  return (
    <span className="analytics-help" title={reason}>
      <span aria-hidden="true">—</span>
      <span className="sr-only">Нет значения: {reason}</span>
      <CircleHelp size={14} aria-hidden="true" />
    </span>
  );
}

function MetricTile({
  label,
  children,
  caption,
}: {
  label: string;
  children: React.ReactNode;
  caption?: string;
}) {
  return (
    <article className="analytics-metric card-surface">
      <span>{label}</span>
      <div className="analytics-metric-value-row">
        <strong className="tabular-nums">{children}</strong>
      </div>
      {caption && <small>{caption}</small>}
    </article>
  );
}

function MetricsSkeleton() {
  return (
    <div className="analytics-metrics-grid" aria-busy="true">
      {[1, 2, 3, 4, 5, 6].map((item) => (
        <div className="analytics-metric card-surface" key={item}>
          <Skeleton className="short" />
          <Skeleton className="large" />
        </div>
      ))}
    </div>
  );
}

export function SummarySection({ filters }: { filters: AnalyticsFilters }) {
  const { data, error, mutate } = useSummary(filters);
  if (error) return <ErrorState error={error} retry={() => void mutate()} />;
  if (!data) return <MetricsSkeleton />;
  const currency = data.currency_code;
  const money = (value: string) => formatMoney(value, currency, { hideZeroCents: true });
  if (data.transaction_count === 0) {
    return (
      <EmptyState
        title="Нет операций за период"
        description="Добавьте операции или импортируйте выписку, чтобы увидеть аналитику"
        action={
          <Link className="button secondary" href="/transactions">
            К операциям
          </Link>
        }
      />
    );
  }
  return (
    <section className="analytics-metrics-grid" aria-label="Итоги периода">
      <MetricTile label="Доходы">{money(data.income)}</MetricTile>
      <MetricTile
        label="Расходы"
        caption={`Валовые ${money(data.gross_expenses)} · возвраты ${money(data.refunds)}`}
      >
        {money(data.net_expenses)}
      </MetricTile>
      <MetricTile label="Денежный поток" caption="Денежный поток за период (не остаток на счёте)">
        {money(data.net_cash_flow)}
      </MetricTile>
      <MetricTile label="Норма сбережений">
        <NullableValue
          value={data.savings_rate === null ? null : formatPercent(data.savings_rate, true)}
          reason="Нет доходов за период — норма сбережений не рассчитывается"
        />
      </MetricTile>
      <MetricTile
        label="Переводы"
        caption="Поступления / списания. Переводы между своими счетами не учитываются в доходах и расходах"
      >
        {money(data.transfers_in)} / {money(data.transfers_out)}
      </MetricTile>
      <MetricTile label="Операций">{String(data.transaction_count)}</MetricTile>
    </section>
  );
}

function ChangeCell({ entry, lowerIsBetter }: { entry: MetricChange; lowerIsBetter: boolean }) {
  if (entry.change_percent === null) {
    return <NullableValue value={null} reason="В прошлом месяце было 0 — процент не считается" />;
  }
  const negative = entry.change_percent.startsWith("-");
  const zero = /^[+-]?0*(\.0*)?$/.test(entry.change_percent);
  const favorable = lowerIsBetter ? negative : !negative;
  const text = `${negative ? "−" : "+"}${formatPercent(entry.change_percent.replace(/^[+-]/, ""), true)}`;
  return (
    <span className={zero ? undefined : favorable ? "text-positive" : "text-negative"}>
      {text}
      <span className="sr-only">{zero ? "" : favorable ? " (лучше)" : " (хуже)"}</span>
    </span>
  );
}

/** `month` is `YYYY-MM` of the period end — never the currency. */
export function ComparisonSection({ month, currency }: { month: string; currency: string }) {
  const { data, error, mutate } = useComparison(month, currency);
  return (
    <section className="entity-section analytics-comparison card-surface">
      <header>
        <div>
          <h2>Сравнение с прошлым месяцем</h2>
          <p>
            {data
              ? `${formatMonth(data.current.month)} к ${formatMonth(data.previous.month)}`
              : formatMonth(month)}
            {" · месяц окончания выбранного периода"}
          </p>
        </div>
      </header>
      {error ? (
        <ErrorState error={error} retry={() => void mutate()} />
      ) : !data ? (
        <div aria-busy="true">
          <Skeleton className="large" />
          <Skeleton className="medium" />
        </div>
      ) : (
        <>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Показатель</th>
                  <th scope="col">Текущий</th>
                  <th scope="col">Прошлый</th>
                  <th scope="col">Изменение</th>
                </tr>
              </thead>
              <tbody>
                {(
                  [
                    ["Доход", data.income, false],
                    ["Расходы", data.net_expenses, true],
                    ["Денежный поток", data.net_cash_flow, false],
                  ] as const
                ).map(([label, entry, lowerIsBetter]) => (
                  <tr key={label}>
                    <th scope="row">{label}</th>
                    <td>
                      {formatMoney(entry.current, data.currency_code, { hideZeroCents: true })}
                    </td>
                    <td>
                      {formatMoney(entry.previous, data.currency_code, { hideZeroCents: true })}
                    </td>
                    <td>
                      <ChangeCell entry={entry} lowerIsBetter={lowerIsBetter} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="analytics-pp">
            Изменение нормы сбережений:{" "}
            <NullableValue
              value={
                data.savings_rate_change_pp === null ? null : formatPp(data.savings_rate_change_pp)
              }
              reason="Норма сбережений не рассчитывается в одном из месяцев (нет доходов)"
            />
          </p>
        </>
      )}
    </section>
  );
}

export function MonthlySection({ year, currency }: { year: number; currency: string }) {
  const { data, error, mutate } = useMonthly(year, currency);
  const [showTable, setShowTable] = useState(false);
  return (
    <section className="chart-card card-surface analytics-monthly">
      <header>
        <div>
          <h2>Доходы и расходы по месяцам</h2>
          <p>{year} год</p>
        </div>
        <button
          type="button"
          className="button secondary"
          aria-expanded={showTable}
          disabled={!data}
          onClick={() => setShowTable((value) => !value)}
        >
          {showTable ? "Скрыть таблицу" : "Показать таблицей"}
        </button>
      </header>
      {error ? (
        <ErrorState error={error} retry={() => void mutate()} />
      ) : !data ? (
        <div className="chart-wrap" aria-busy="true" aria-label="Загрузка графика">
          <Skeleton className="large" />
        </div>
      ) : (
        <>
          <MonthlyChart data={data} />
          {showTable && <MonthlyTable data={data} />}
        </>
      )}
    </section>
  );
}

export function AnalyticsOverview() {
  const state = useAnalyticsFilterStateFromUrl();
  const { filters, range, currency } = state;
  return (
    <div className="entity-page analytics-page">
      <PageHeader
        title="Аналитика"
        description="Доходы, расходы и движение денег"
        actions={
          <Link className="button secondary" href={`/analytics/details?${filtersQuery(state)}`}>
            Детальная аналитика
          </Link>
        }
      />
      <AnalyticsFiltersPanel state={state} />
      {filters && (
        <>
          <SummarySection filters={filters} />
          <ComparisonSection month={monthOf(range.to)} currency={currency} />
          <MonthlySection year={yearOf(range.to)} currency={currency} />
        </>
      )}
    </div>
  );
}

export function AnalyticsOverviewScreen() {
  return (
    <AppShell>
      <AnalyticsOverview />
    </AppShell>
  );
}
