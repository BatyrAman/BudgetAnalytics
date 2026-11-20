"use client";

import Link from "next/link";
import { useState } from "react";

import { AppShell } from "@/components/app-shell";
import { EmptyState, ErrorState, PageHeader, SkeletonCard } from "@/components/common";
import { useBudgetUtilizations, useBudgets, useCategories } from "@/lib/api/hooks";
import { formatMoney, formatPercent } from "@/lib/format";
import { usePreviewState } from "@/lib/preview";
import type { Budget, BudgetUtilization, Category } from "@/lib/types";

import { BudgetForm } from "./budget-form";
import { BudgetCategory, useRevalidateBudgets } from "./budget-shared";
import { UsageBar, UsageStatusBadge, usageTone } from "./budget-usage";
import { currentMonth, monthLabel } from "./month";
import { useTimezone } from "./use-timezone";
import "./budgets.css";

const PAGE_SIZE = 20;

function BudgetCard({
  budget,
  usage,
  usageState,
  categories,
}: {
  budget: Budget;
  usage: BudgetUtilization | undefined;
  usageState: "loading" | "error" | "ready";
  categories: Category[] | undefined;
}) {
  return (
    <Link className="budget-card card-surface" href={`/budgets/${budget.id}`}>
      <div className="budget-card-heading">
        <div>
          <h2>{budget.title}</h2>
          <BudgetCategory budget={budget} categories={categories} />
        </div>
        {usage && <UsageStatusBadge usage={usage} />}
      </div>
      {usage ? (
        <>
          <p className="budget-amounts">
            <strong>{formatMoney(usage.spent, usage.currency_code)}</strong>
            <span>из</span>
            <strong>{formatMoney(usage.limit, usage.currency_code)}</strong>
          </p>
          <UsageBar usage={usage} label={`Использование бюджета ${budget.title}`} />
          <div className="budget-progress-meta">
            <span className={`budget-progress-label ${usageTone(usage)}`}>
              {formatPercent(usage.utilization_percent, true)}
            </span>
          </div>
        </>
      ) : usageState === "loading" ? (
        <div className="budget-card-loading" aria-label="Загрузка использования" />
      ) : (
        <p className="budget-amounts">
          <span>Лимит</span>
          <strong>{formatMoney(budget.monthly_limit, budget.currency_code)}</strong>
          <span>· использование недоступно</span>
        </p>
      )}
    </Link>
  );
}

function BudgetsContent({ timeZone }: { timeZone: string }) {
  const month = currentMonth(timeZone);
  const preview = usePreviewState();
  const [offset, setOffset] = useState(0);
  const [formOpen, setFormOpen] = useState(false);
  const budgets = useBudgets({ limit: PAGE_SIZE, offset });
  const usages = useBudgetUtilizations(month);
  const { data: categories } = useCategories();
  const revalidate = useRevalidateBudgets();

  const page = budgets.data;
  const usageById = new Map((usages.data ?? []).map((item) => [item.budget_id, item]));
  const exceeded = (usages.data ?? []).filter((item) => item.is_exceeded).length;
  const usageState = usages.error ? "error" : usages.data ? "ready" : "loading";
  const openForm = () => setFormOpen(true);

  let body: React.ReactNode;
  if (preview === "error" || budgets.error) {
    body = <ErrorState error={budgets.error} retry={() => void budgets.mutate()} />;
  } else if (preview === "loading" || !page) {
    body = (
      <div className="budget-grid" aria-busy="true">
        {[1, 2, 3].map((item) => (
          <SkeletonCard key={item} />
        ))}
      </div>
    );
  } else if (preview === "empty" || page.total === 0) {
    body = (
      <EmptyState
        title="Бюджетов пока нет"
        description="Создайте первый бюджет, чтобы контролировать расходы"
        action={
          <button type="button" className="button primary" onClick={openForm}>
            Создать бюджет
          </button>
        }
      />
    );
  } else {
    body = (
      <>
        {usages.error && (
          <ErrorState
            title="Не удалось загрузить использование бюджетов"
            error={usages.error}
            retry={() => void usages.mutate()}
          />
        )}
        <div className="budget-grid">
          {page.items.map((budget) => (
            <BudgetCard
              key={budget.id}
              budget={budget}
              usage={usageById.get(budget.id)}
              usageState={usageState}
              categories={categories}
            />
          ))}
        </div>
        {page.total > PAGE_SIZE && (
          <nav className="budget-pagination" aria-label="Страницы бюджетов">
            <span>
              {page.offset + 1}–{page.offset + page.items.length} из {page.total}
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
    );
  }

  return (
    <div className="entity-page budget-page">
      <PageHeader
        title="Бюджеты"
        description={`${monthLabel(month)} · использование за текущий месяц`}
        actions={
          <button type="button" className="button primary" onClick={openForm}>
            Создать бюджет
          </button>
        }
      />
      {usages.data && usages.data.length > 0 && preview === "default" && (
        <section className="budget-overview-strip card-surface" aria-label="Сводка по бюджетам">
          <span>Превышено</span>
          <strong>
            {exceeded} из {usages.data.length}
          </strong>
          <span>бюджетов</span>
        </section>
      )}
      {body}
      {formOpen && <BudgetForm onClose={() => setFormOpen(false)} onSaved={revalidate} />}
    </div>
  );
}

export function BudgetsScreen() {
  const timeZone = useTimezone();
  return (
    <AppShell>
      {timeZone ? (
        <BudgetsContent timeZone={timeZone} />
      ) : (
        <div className="budget-grid" aria-busy="true">
          <SkeletonCard />
        </div>
      )}
    </AppShell>
  );
}
