"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { EmptyState, ErrorState, Skeleton, StatusBadge } from "@/components/common";
import { formatDate, formatMoney, formatPercent, signForType } from "@/lib/format";
import type { Account, Category, Overview, Page, Transaction } from "@/lib/types";

export const metricMoney = (value: string, currency: string) =>
  formatMoney(value, currency, { hideZeroCents: true });

/** «—» for a missing value, with the reason as a tooltip and as screen-reader text. */
export function NullValue({ hint }: { hint: string }) {
  return (
    <span className="null-value" title={hint}>
      <span aria-hidden="true">—</span>
      <span className="sr-only">Нет данных: {hint}</span>
    </span>
  );
}

export function Welcome() {
  return (
    <section className="welcome card-surface">
      <div>
        <span className="overline">НАЧНИТЕ ЗДЕСЬ</span>
        <h2>Ваши финансы — под контролем</h2>
        <p>Добавьте данные, чтобы увидеть полную картину расходов и накоплений.</p>
      </div>
      <div className="welcome-steps">
        <Link href="/accounts">
          <span>1</span>
          <b>Добавьте счёт</b>
          <ArrowRight aria-hidden="true" />
        </Link>
        <Link href="/transactions?new=1">
          <span>2</span>
          <b>Добавьте операцию</b>
          <ArrowRight aria-hidden="true" />
        </Link>
        <Link href="/transactions/import">
          <span>3</span>
          <b>Импортируйте выписку</b>
          <ArrowRight aria-hidden="true" />
        </Link>
      </div>
    </section>
  );
}

const budgetTone = (budget: Overview["budgets"][number]) =>
  budget.is_exceeded
    ? "exceeded"
    : // Threshold colouring only (D-7: warning at ≥ 80 %).
      Number(budget.utilization_percent) >= 80
      ? "warning"
      : "normal";

export function BudgetsBlock({ overview }: { overview: Overview }) {
  const currency = overview.currency_code;
  if (overview.budgets.length === 0) {
    return (
      <EmptyState
        title="Нет бюджетов"
        description={`В ${currency} пока не настроены бюджеты на этот месяц.`}
      />
    );
  }
  return (
    <div className="budget-list">
      {overview.budgets.map((budget) => {
        const tone = budgetTone(budget);
        // Bar width is geometry only, capped at 100 %.
        const width = Math.min(Math.max(Number(budget.utilization_percent) || 0, 0), 100);
        return (
          <div className="budget-item" key={budget.budget_id}>
            <div className="budget-head">
              <b>{budget.title}</b>
              <StatusBadge
                tone={
                  tone === "exceeded" ? "negative" : tone === "warning" ? "warning" : "positive"
                }
              >
                {formatPercent(budget.utilization_percent)}
              </StatusBadge>
            </div>
            <div
              className="progress-track"
              role="progressbar"
              aria-label={`Бюджет «${budget.title}»`}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={width}
              aria-valuetext={formatPercent(budget.utilization_percent)}
            >
              <div
                className={`progress-fill ${tone === "normal" ? "" : tone}`}
                style={{ width: `${width}%` }}
              />
            </div>
            <div className="budget-foot">
              <span>
                {metricMoney(budget.spent, currency)} из {metricMoney(budget.limit, currency)}
              </span>
              {budget.is_exceeded && <b className="text-negative">Превышен</b>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function IndicatorsBlock({ overview }: { overview: Overview }) {
  const indicator = overview.indicators;
  const currency = overview.currency_code;
  return (
    <div className="indicator-list">
      <div>
        <span>Подушка безопасности</span>
        <b>
          {indicator.emergency_fund_months == null ? (
            <NullValue hint="Не рассчитывается: нет счетов в этой валюте или расходов за последние 3 месяца" />
          ) : (
            `${formatPercent(indicator.emergency_fund_months).replace(/ %$/, "")} мес.`
          )}
        </b>
      </div>
      <div>
        <span>Средние расходы за 3 полных месяца</span>
        <b>
          {indicator.average_monthly_expenses_3m == null ? (
            <NullValue hint="Недостаточно данных о расходах за последние 3 месяца" />
          ) : (
            metricMoney(indicator.average_monthly_expenses_3m, currency)
          )}
        </b>
      </div>
      <div>
        <span>Расходы к доходам</span>
        <b>
          {indicator.expense_to_income_percent == null ? (
            <NullValue hint="Не считается без доходов за месяц" />
          ) : (
            formatPercent(indicator.expense_to_income_percent)
          )}
        </b>
      </div>
      <div>
        <span>Депозиты</span>
        <b>{metricMoney(indicator.deposits_principal, currency)}</b>
      </div>
      <div>
        <span>Ожидаемый доход по депозитам</span>
        <b className="text-positive">
          {formatMoney(indicator.deposits_expected_interest, currency, {
            hideZeroCents: true,
            sign: "+",
          })}
        </b>
      </div>
    </div>
  );
}

export function RecentTransactions({
  page,
  error,
  retry,
  categories,
  accounts,
}: {
  page: Page<Transaction> | undefined;
  error: unknown;
  retry: () => void;
  categories: Category[] | undefined;
  accounts: Account[] | undefined;
}) {
  return (
    <section className="recent-card card-surface">
      <div className="section-header">
        <div>
          <h3>Последние операции</h3>
          <p>Недавние движения по счетам</p>
        </div>
        <Link className="text-link" href="/transactions">
          Все операции <ArrowRight size={15} aria-hidden="true" />
        </Link>
      </div>
      {error ? (
        <ErrorState error={error} retry={retry} />
      ) : !page ? (
        <div aria-busy="true">
          {[1, 2, 3].map((row) => (
            <Skeleton key={row} className="medium" />
          ))}
        </div>
      ) : page.items.length === 0 ? (
        <EmptyState
          title="Операций пока нет"
          description="Добавьте операцию вручную или импортируйте выписку."
        />
      ) : (
        <>
          <div className="table-scroll">
            <table className="transactions-table">
              <thead>
                <tr>
                  <th>Операция</th>
                  <th>Категория</th>
                  <th>Счёт</th>
                  <th>Дата</th>
                  <th className="align-right">Сумма</th>
                </tr>
              </thead>
              <tbody>
                {page.items.map((transaction) => {
                  const category = categories?.find((item) => item.id === transaction.category_id);
                  const account = accounts?.find((item) => item.id === transaction.account_id);
                  const sign = signForType(transaction.transaction_type);
                  const positive = sign === "+";
                  return (
                    <tr key={transaction.id}>
                      <td>
                        <span className="transaction-title">
                          <span
                            className={`transaction-mark ${positive ? "positive-mark" : ""}`}
                            aria-hidden="true"
                          >
                            {sign ?? "·"}
                          </span>
                          <span>{transaction.description || "Без описания"}</span>
                        </span>
                      </td>
                      <td>{category?.name ?? "—"}</td>
                      <td>{account?.name ?? "—"}</td>
                      <td>{formatDate(transaction.transaction_date)}</td>
                      <td className={`align-right tabular-nums ${positive ? "text-positive" : ""}`}>
                        {formatMoney(transaction.amount, transaction.currency_code, { sign })}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {/* Phones: the table is hidden by CSS and this compact list is shown instead. */}
          <ul className="mobile-transactions" aria-label="Последние операции">
            {page.items.map((transaction) => {
              const category = categories?.find((item) => item.id === transaction.category_id);
              const sign = signForType(transaction.transaction_type);
              const positive = sign === "+";
              return (
                <li className="mobile-transaction" key={transaction.id}>
                  <span
                    className={`transaction-mark ${positive ? "positive-mark" : ""}`}
                    aria-hidden="true"
                  >
                    {sign ?? "·"}
                  </span>
                  <div>
                    <b>{transaction.description || "Без описания"}</b>
                    <small>
                      {category?.name ?? "Без категории"} ·{" "}
                      {formatDate(transaction.transaction_date)}
                    </small>
                  </div>
                  <strong className={`tabular-nums ${positive ? "text-positive" : ""}`}>
                    {formatMoney(transaction.amount, transaction.currency_code, { sign })}
                  </strong>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </section>
  );
}
