"use client";

import Link from "next/link";
import { useState } from "react";

import { AppShell } from "@/components/app-shell";
import { EmptyState, ErrorState, PageHeader, Skeleton, SkeletonCard } from "@/components/common";
import { useBanks, useDefaultCurrency, useDeposits, useOverview } from "@/lib/api/hooks";
import { formatDate, formatMoney, formatPercent } from "@/lib/format";
import type { Bank, Deposit } from "@/lib/types";

import { DepositFormDialog } from "./deposit-form";
import {
  CAPITALIZATION_LABELS,
  DATA_ISSUE_LABELS,
  bankInitials,
  formatRateExact,
} from "./deposit-utils";

const PAGE_SIZE = 10;

function DepositCard({
  deposit,
  bank,
  onEdit,
}: {
  deposit: Deposit;
  bank: Bank | undefined;
  onEdit: (deposit: Deposit) => void;
}) {
  const currency = deposit.currency_code;
  return (
    <article className="deposit-card card-surface">
      <Link href={`/deposits/${deposit.id}`} className="deposit-card-main">
        <span className="bank-initials" aria-hidden="true">
          {bank ? bankInitials(bank.name) : "Б"}
        </span>
        <div className="deposit-card-title">
          <h2>{bank?.name ?? "Банк"}</h2>
          <small>
            {formatDate(deposit.start_date)} – {formatDate(deposit.end_date)}
          </small>
        </div>
        <strong className="deposit-principal">{formatMoney(deposit.principal, currency)}</strong>
      </Link>
      <div className="deposit-card-meta">
        <span>
          Номинальная ставка <b>{formatPercent(deposit.interest_rate, true)}</b>
        </span>
        <span>
          ГЭСВ (по данным банка){" "}
          <b>{deposit.effective_rate === null ? "—" : formatRateExact(deposit.effective_rate)}</b>
        </span>
        <span>
          Капитализация <b>{CAPITALIZATION_LABELS[deposit.capitalization]}</b>
        </span>
        {deposit.maturity ? (
          <>
            <span>
              Доход к концу срока <b>{formatMoney(deposit.maturity.interest, currency)}</b>
            </span>
            <span>
              Сумма к концу срока <b>{formatMoney(deposit.maturity.maturity_amount, currency)}</b>
            </span>
          </>
        ) : (
          <span className="deposit-data-issue" role="status">
            Расчёт недоступен: {deposit.data_issue ? DATA_ISSUE_LABELS[deposit.data_issue] : ""}{" "}
            Исправьте даты — вклад не учитывается в итогах.
          </span>
        )}
      </div>
      <button
        type="button"
        className="button secondary deposit-edit"
        onClick={() => onEdit(deposit)}
        aria-label={`Изменить депозит ${bank?.name ?? ""}`.trim()}
      >
        Изменить
      </button>
    </article>
  );
}

/** «Сумма вкладов» / «Ожидаемый доход» from `/dashboard/overview` — no client sums. */
function DepositTotals({ currency }: { currency: string }) {
  const { data, error, mutate } = useOverview(currency);
  if (error) return <ErrorState error={error} retry={() => void mutate()} />;
  if (!data) {
    return (
      <section className="deposit-summary-grid" aria-busy="true">
        <div className="analytics-metric card-surface">
          <Skeleton className="large" />
        </div>
        <div className="analytics-metric card-surface">
          <Skeleton className="large" />
        </div>
      </section>
    );
  }
  const code = data.currency_code;
  return (
    <section className="deposit-summary-grid" aria-label="Итоги по вкладам">
      <article className="analytics-metric card-surface">
        <span>Сумма вкладов</span>
        <strong className="tabular-nums">
          {formatMoney(data.indicators.deposits_principal, code, { hideZeroCents: true })}
        </strong>
        <small>Только вклады в {code}</small>
      </article>
      <article className="analytics-metric card-surface">
        <span>Ожидаемый доход</span>
        <strong className="tabular-nums">
          {formatMoney(data.indicators.deposits_expected_interest, code, { hideZeroCents: true })}
        </strong>
        <small>Оценка; расчёт банка может отличаться</small>
      </article>
    </section>
  );
}

export function DepositsList() {
  const [offset, setOffset] = useState(0);
  const [editing, setEditing] = useState<Deposit | null>(null);
  const [creating, setCreating] = useState(false);
  const defaultCurrency = useDefaultCurrency();
  const [summaryCurrency, setSummaryCurrency] = useState<string | null>(null);
  const { data: page, error, mutate } = useDeposits({ limit: PAGE_SIZE, offset });
  const { data: banks } = useBanks();

  const currencies = [
    ...new Set([defaultCurrency, ...(page?.items.map((item) => item.currency_code) ?? [])]),
  ];
  const currency = summaryCurrency ?? defaultCurrency;
  const addButton = (
    <button type="button" className="button primary" onClick={() => setCreating(true)}>
      Добавить депозит
    </button>
  );

  return (
    <div className="entity-page deposits-page">
      <PageHeader
        title="Депозиты"
        description="Сбережения и ожидаемый доход"
        actions={
          <>
            <Link className="button secondary" href="/deposits/calculator">
              Калькулятор
            </Link>
            {addButton}
          </>
        }
      />
      {currencies.length > 1 && (
        <label className="analytics-currency">
          <span>Валюта итогов </span>
          <select value={currency} onChange={(event) => setSummaryCurrency(event.target.value)}>
            {currencies.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </label>
      )}
      <DepositTotals currency={currency} />
      {error ? (
        <ErrorState error={error} retry={() => void mutate()} />
      ) : !page ? (
        <div className="deposit-list" aria-busy="true">
          {[1, 2].map((item) => (
            <SkeletonCard key={item} />
          ))}
        </div>
      ) : page.total === 0 ? (
        <EmptyState
          title="Депозитов пока нет"
          description="Добавьте депозит, чтобы отслеживать срок и доход"
          action={addButton}
        />
      ) : (
        <>
          <div className="deposit-list">
            {page.items.map((deposit) => (
              <DepositCard
                key={deposit.id}
                deposit={deposit}
                bank={banks?.find((bank) => bank.id === deposit.bank_id)}
                onEdit={setEditing}
              />
            ))}
          </div>
          {page.total > PAGE_SIZE && (
            <nav className="budget-pagination" aria-label="Страницы депозитов">
              <span>
                {offset + 1}–{Math.min(offset + page.items.length, page.total)} из {page.total}
              </span>
              <div>
                <button
                  type="button"
                  className="button secondary"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                >
                  Назад
                </button>
                <button
                  type="button"
                  className="button secondary"
                  disabled={offset + PAGE_SIZE >= page.total}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                >
                  Далее
                </button>
              </div>
            </nav>
          )}
        </>
      )}
      {(creating || editing) && (
        <DepositFormDialog
          deposit={editing ?? undefined}
          onClose={() => {
            setCreating(false);
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}

export function DepositsListScreen() {
  return (
    <AppShell>
      <DepositsList />
    </AppShell>
  );
}
