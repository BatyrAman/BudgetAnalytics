"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ArrowRight, Plus } from "lucide-react";
import { StatePreviewSwitcher } from "@/components/app-shell";
import { ChartCard, EmptyState, ErrorState, MetricCard, SkeletonCard } from "@/components/common";
import { CashflowChart, ExpenseDonut } from "@/components/dashboard-charts";
import { currentTimezone } from "@/lib/api/client";
import {
  useAccounts,
  useCategories,
  useCategoryBreakdown,
  useDefaultCurrency,
  useMonthly,
  useOverview,
  useTransactions,
} from "@/lib/api/hooks";
import { formatMonth, formatPercent } from "@/lib/format";
import { usePreviewState } from "@/lib/preview";
import {
  BudgetsBlock,
  IndicatorsBlock,
  RecentTransactions,
  Welcome,
  metricMoney,
} from "./dashboard-blocks";
import { currentYearMonth } from "./period";
import "./dashboard.css";

const RECENT = { limit: 5 } as const;
const capitalize = (value: string) => value.charAt(0).toUpperCase() + value.slice(1);

function LoadingDashboard() {
  return (
    <>
      <div className="metrics-grid" aria-busy="true">
        {[1, 2, 3, 4].map((item) => (
          <SkeletonCard key={item} />
        ))}
      </div>
      <div className="dashboard-grid">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    </>
  );
}

export function DashboardContent() {
  const preview = usePreviewState();
  const profileCurrency = useDefaultCurrency();
  // No currency is sent until the user picks one: the backend then uses the
  // user's own default currency (G-4). This avoids a first request in KZT
  // followed by a second one once the profile loads, and does not depend on
  // the profile request succeeding.
  const [selected, setSelected] = useState<string | null>(null);
  const requested = selected ?? undefined;
  const now = useMemo(() => currentYearMonth(currentTimezone()), []);

  const overviewQuery = useOverview(requested);
  const monthlyQuery = useMonthly(now.year, requested);
  const breakdownQuery = useCategoryBreakdown("expense", requested ? { currency: requested } : {});
  /** The currency actually shown: the user's pick, else what the backend answered with. */
  const currency = selected ?? overviewQuery.data?.currency_code ?? profileCurrency;
  const defaultCurrency = overviewQuery.data?.currency_code ?? profileCurrency;
  const transactionsQuery = useTransactions(RECENT);
  const categoriesQuery = useCategories();
  const accountsQuery = useAccounts();

  const accounts = accountsQuery.data;
  const currencies = useMemo(() => {
    const own = new Set((accounts ?? []).map((account) => account.currency_code));
    own.delete(defaultCurrency);
    return [defaultCurrency, ...[...own].sort()];
  }, [accounts, defaultCurrency]);

  const overview = overviewQuery.data;
  const monthTitle = overview ? capitalize(formatMonth(overview.month)) : "";
  const currentMonth = overview?.month ?? now.month;
  const isEmpty =
    preview === "empty" ||
    (accounts?.length === 0 && transactionsQuery.data?.total === 0 && preview === "default");

  let body: React.ReactNode;
  if (preview === "loading") body = <LoadingDashboard />;
  else if (preview === "error") body = <ErrorState retry={() => void overviewQuery.mutate()} />;
  else if (isEmpty) body = <Welcome />;
  else if (overviewQuery.error)
    body = <ErrorState error={overviewQuery.error} retry={() => void overviewQuery.mutate()} />;
  else if (!overview) body = <LoadingDashboard />;
  else {
    const indicator = overview.indicators;
    body = (
      <>
        <div className="metrics-grid">
          {overview.current_balance == null ? (
            <MetricCard
              label="Баланс счетов"
              value={`Нет счетов в ${currency}`}
              caption="Добавьте счёт в этой валюте"
            />
          ) : (
            <MetricCard
              label="Баланс счетов"
              value={metricMoney(overview.current_balance, currency)}
              caption="Сумма активных счетов, без конвертации"
            />
          )}
          <MetricCard
            label="Доходы месяца"
            value={metricMoney(overview.monthly_income, currency)}
            change={indicator.income_change_percent}
            caption="к прошлому месяцу"
          />
          <MetricCard
            label="Расходы месяца"
            value={metricMoney(overview.monthly_expenses, currency)}
            change={indicator.expense_change_percent}
            lowerIsBetter
            caption="к прошлому месяцу, за вычетом возвратов"
          />
          {indicator.savings_rate == null ? (
            <div className="metric-hint" title="Норма сбережений не считается без доходов">
              <MetricCard
                label="Норма сбережений"
                value="—"
                caption="Не считается без доходов за месяц"
              />
            </div>
          ) : (
            <MetricCard
              label="Норма сбережений"
              value={formatPercent(indicator.savings_rate)}
              caption={`Денежный поток: ${metricMoney(overview.monthly_net_cash_flow, currency)}`}
            />
          )}
        </div>
        <div className="dashboard-grid">
          <ChartCard title="Денежный поток" subtitle={`${now.year} · не остаток на счёте`}>
            <div className="chart-legend">
              <span>
                <i className="legend-dot income-dot" aria-hidden="true" />
                Доход
              </span>
              <span>
                <i className="legend-dot expense-dot" aria-hidden="true" />
                Расход
              </span>
            </div>
            {monthlyQuery.error ? (
              <ErrorState error={monthlyQuery.error} retry={() => void monthlyQuery.mutate()} />
            ) : !monthlyQuery.data ? (
              <SkeletonCard />
            ) : (
              <CashflowChart data={monthlyQuery.data} currentMonth={currentMonth} />
            )}
          </ChartCard>
          <ChartCard title="Структура расходов" subtitle={monthTitle}>
            {breakdownQuery.error ? (
              <ErrorState error={breakdownQuery.error} retry={() => void breakdownQuery.mutate()} />
            ) : !breakdownQuery.data ? (
              <SkeletonCard />
            ) : breakdownQuery.data.items.length === 0 ? (
              <EmptyState
                title="Нет расходов"
                description={`В ${currency} за этот месяц расходов пока нет.`}
              />
            ) : (
              <ExpenseDonut data={breakdownQuery.data} />
            )}
          </ChartCard>
          <ChartCard
            title="Бюджеты месяца"
            subtitle={`Использовано за ${formatMonth(overview.month)}`}
          >
            <BudgetsBlock overview={overview} />
            <Link href="/budgets" className="text-link">
              Все бюджеты <ArrowRight size={15} aria-hidden="true" />
            </Link>
          </ChartCard>
          <ChartCard title="Показатели" subtitle="Финансовые ориентиры">
            <IndicatorsBlock overview={overview} />
            <Link href="/deposits" className="text-link">
              Депозиты <ArrowRight size={15} aria-hidden="true" />
            </Link>
          </ChartCard>
        </div>
        <RecentTransactions
          page={transactionsQuery.data}
          error={transactionsQuery.error}
          retry={() => void transactionsQuery.mutate()}
          categories={categoriesQuery.data}
          accounts={accounts}
        />
      </>
    );
  }

  return (
    <div className="dashboard-content">
      <div className="state-row">
        <StatePreviewSwitcher />
      </div>
      <div className="dashboard-toolbar">
        <div>
          <span className="overline">ТЕКУЩИЙ МЕСЯЦ</span>
          <h2>{monthTitle || "Обзор"}</h2>
        </div>
        {currencies.length > 1 && (
          <label className="currency-select">
            Валюта
            <select
              aria-label="Валюта отчёта"
              value={currency}
              onChange={(event) => setSelected(event.target.value)}
            >
              {currencies.map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </select>
          </label>
        )}
        <Link className="button primary desktop-add" href="/transactions?new=1">
          <Plus size={16} aria-hidden="true" /> Добавить операцию
        </Link>
      </div>
      {body}
    </div>
  );
}
