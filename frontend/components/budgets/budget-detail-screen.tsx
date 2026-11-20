"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AppShell } from "@/components/app-shell";
import { ErrorState, PageHeader, SkeletonCard } from "@/components/common";
import { deleteBudget } from "@/lib/api/client";
import { toUserMessage } from "@/lib/api/errors";
import { useBudget, useBudgetUtilization, useCategories } from "@/lib/api/hooks";
import { formatMoney, formatPercent } from "@/lib/format";
import type { Budget } from "@/lib/types";

import { BudgetForm } from "./budget-form";
import { BudgetCategory, useRevalidateBudgets } from "./budget-shared";
import { BudgetTransactions } from "./budget-transactions";
import { UsageBar, UsageStatusBadge } from "./budget-usage";
import { currentMonth, monthLabel, recentMonths, shiftMonth } from "./month";
import { useTimezone } from "./use-timezone";
import "./budgets.css";
import { ConfirmDialog } from "@/components/confirm-dialog";

const HISTORY_MONTHS = 24;

function MonthSwitcher({
  month,
  latest,
  onChange,
}: {
  month: string;
  latest: string;
  onChange: (month: string) => void;
}) {
  const options = recentMonths(latest, HISTORY_MONTHS);
  return (
    <section className="budget-detail-month" aria-label="Выбор месяца">
      <button
        type="button"
        className="button secondary month-arrow"
        onClick={() => onChange(shiftMonth(month, -1))}
        disabled={month === options[0]}
        aria-label="Предыдущий месяц"
      >
        ‹
      </button>
      <strong className="desktop-month-label" aria-live="polite">
        {monthLabel(month)}
      </strong>
      <label className="mobile-month-select">
        <span className="sr-only">Месяц</span>
        <select value={month} onChange={(event) => onChange(event.target.value)}>
          {options.map((option) => (
            <option key={option} value={option}>
              {monthLabel(option)}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        className="button secondary month-arrow"
        onClick={() => onChange(shiftMonth(month, 1))}
        disabled={month >= latest}
        aria-label="Следующий месяц"
      >
        ›
      </button>
    </section>
  );
}

function UsageSection({ id, month, timeZone }: { id: number; month: string; timeZone: string }) {
  const { data: usage, error, mutate } = useBudgetUtilization(id, month);
  if (error) return <ErrorState error={error} retry={() => void mutate()} />;
  if (!usage) {
    return (
      <div className="budget-metrics-grid" aria-busy="true">
        {[1, 2, 3, 4].map((item) => (
          <SkeletonCard key={item} />
        ))}
      </div>
    );
  }
  return (
    <>
      <section className="budget-metrics-grid">
        <article className="budget-metric card-surface">
          <span>Лимит</span>
          <strong>{formatMoney(usage.limit, usage.currency_code)}</strong>
        </article>
        <article className="budget-metric card-surface">
          <span>Использовано</span>
          <strong>{formatMoney(usage.spent, usage.currency_code)}</strong>
        </article>
        <article className="budget-metric card-surface">
          <span>Остаток</span>
          <strong className={usage.remaining.startsWith("-") ? "text-negative" : ""}>
            {formatMoney(usage.remaining, usage.currency_code)}
          </strong>
        </article>
        <article className="budget-metric card-surface">
          <span>Использовано, %</span>
          <strong>{formatPercent(usage.utilization_percent, true)}</strong>
        </article>
      </section>
      <div className="budget-detail-progress">
        <UsageBar usage={usage} label="Использование лимита" />
        <UsageStatusBadge usage={usage} />
      </div>
      <p className="budget-timezone-note">
        Использовано = расходы − возвраты за календарный месяц ({timeZone}) в категории и валюте
        бюджета.
      </p>
    </>
  );
}

function DeleteBudgetDialog({
  budget,
  onClose,
  onDeleted,
}: {
  budget: Budget;
  onClose: () => void;
  onDeleted: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function confirm() {
    setBusy(true);
    setError("");
    try {
      await deleteBudget(budget.id);
      await onDeleted();
    } catch (reason) {
      setError(toUserMessage(reason));
      setBusy(false);
    }
  }
  return (
    <ConfirmDialog
      title="Удалить бюджет?"
      description={<>Бюджет «{budget.title}» будет удалён. Операции не изменятся.</>}
      confirmLabel="Удалить"
      busyLabel="Удаление…"
      danger
      busy={busy}
      error={error || undefined}
      onConfirm={() => void confirm()}
      onCancel={onClose}
    />
  );
}

function BudgetDetail({ id, timeZone }: { id: number; timeZone: string }) {
  const router = useRouter();
  const latest = currentMonth(timeZone);
  const [month, setMonth] = useState(latest);
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const { data: budget, error, mutate } = useBudget(id);
  const { data: categories } = useCategories();
  const revalidate = useRevalidateBudgets();

  if (error) {
    return (
      <div className="entity-page budget-page">
        <Link href="/budgets" className="back-link">
          ← Все бюджеты
        </Link>
        <ErrorState error={error} retry={() => void mutate()} />
      </div>
    );
  }
  if (!budget) return <SkeletonCard />;

  return (
    <div className="entity-page budget-page">
      <Link href="/budgets" className="back-link">
        ← Все бюджеты
      </Link>
      <PageHeader
        title={budget.title}
        description={
          <>
            <BudgetCategory budget={budget} categories={categories} /> · {budget.currency_code}
          </>
        }
        actions={
          <>
            <button type="button" className="button secondary" onClick={() => setEditing(true)}>
              Изменить
            </button>
            <button type="button" className="button danger" onClick={() => setDeleting(true)}>
              Удалить
            </button>
          </>
        }
      />
      <MonthSwitcher month={month} latest={latest} onChange={setMonth} />
      <UsageSection id={id} month={month} timeZone={timeZone} />
      <section className="entity-section budget-transactions">
        <header>
          <h2>Операции месяца</h2>
          <p className="budget-timezone-note">
            Показаны расходы; возвраты учтены в «Использовано».
          </p>
        </header>
        <BudgetTransactions budget={budget} month={month} timeZone={timeZone} />
      </section>
      <p className="budget-history-note">
        История по месяцам одним запросом появится после доработки backend
      </p>
      {deleting && (
        <DeleteBudgetDialog
          budget={budget}
          onClose={() => setDeleting(false)}
          onDeleted={async () => {
            router.push("/budgets");
            await revalidate();
          }}
        />
      )}
      {editing && (
        <BudgetForm budget={budget} onClose={() => setEditing(false)} onSaved={revalidate} />
      )}
    </div>
  );
}

export function BudgetDetailScreen({ id }: { id: number }) {
  const timeZone = useTimezone();
  return (
    <AppShell>
      {timeZone ? <BudgetDetail id={id} timeZone={timeZone} /> : <SkeletonCard />}
    </AppShell>
  );
}
