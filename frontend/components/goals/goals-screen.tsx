"use client";

import Link from "next/link";
import { useState } from "react";
import { Check } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { EmptyState, ErrorState, PageHeader, SkeletonCard } from "@/components/common";
import { useGoals } from "@/lib/api/hooks";
import { formatDate, formatMoney, formatPercent } from "@/lib/format";
import { usePreviewState } from "@/lib/preview";
import type { Goal } from "@/lib/types";

import { GoalForm, useRevalidateGoals } from "./goal-form";
import "./goals.css";

/** Progress bar width capped at 100 % (geometry only); the label shows the API percent. */
export function GoalProgress({ goal }: { goal: Goal }) {
  const percent = Number(goal.progress_percent);
  const width = Number.isFinite(percent) ? Math.max(0, Math.min(percent, 100)) : 0;
  return (
    <div
      className="budget-progress-track"
      role="progressbar"
      aria-label={`Прогресс цели ${goal.name}`}
      aria-valuenow={width}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuetext={formatPercent(goal.progress_percent)}
    >
      <span className="budget-progress-fill" style={{ width: `${width}%` }} />
    </div>
  );
}

export function ReachedBadge() {
  return (
    <span className="goal-reached-badge">
      <Check size={14} aria-hidden="true" /> Цель достигнута
    </span>
  );
}

export function MonthsLeft({ goal }: { goal: Goal }) {
  if (goal.months_left === null) {
    return (
      <span title="Срок не задан или уже прошёл" className="tooltip-help">
        —<span className="sr-only"> (срок не задан или уже прошёл)</span>
      </span>
    );
  }
  return <>{goal.months_left}</>;
}

export function MonthlySaving({ goal }: { goal: Goal }) {
  if (goal.required_monthly_saving === null) return <>—</>;
  return <>{formatMoney(goal.required_monthly_saving, goal.currency_code)} в месяц</>;
}

function GoalCard({ goal }: { goal: Goal }) {
  return (
    <Link className="goal-card card-surface" href={`/goals/${goal.id}`}>
      <div className="goal-card-top">
        <h2>{goal.name}</h2>
        {goal.is_reached && <ReachedBadge />}
      </div>
      <p className="goal-money-line">
        <strong>Накоплено {formatMoney(goal.saved_amount, goal.currency_code)}</strong> из{" "}
        {formatMoney(goal.target_amount, goal.currency_code)}
      </p>
      <GoalProgress goal={goal} />
      <div className="goal-card-footer">
        <span>{formatPercent(goal.progress_percent)}</span>
        <span>Осталось: {formatMoney(goal.remaining, goal.currency_code)}</span>
      </div>
      <dl className="goal-metric-list">
        <div className="goal-metric-row">
          <dt>Срок</dt>
          <dd>{goal.target_date ? formatDate(goal.target_date) : "Без срока"}</dd>
        </div>
        <div className="goal-metric-row">
          <dt>Месяцев до срока</dt>
          <dd>
            <MonthsLeft goal={goal} />
          </dd>
        </div>
        <div className="goal-metric-row">
          <dt>Нужно откладывать</dt>
          <dd>
            <MonthlySaving goal={goal} />
          </dd>
        </div>
      </dl>
      <small className="goal-savings-note">Равными частями, без учёта процентов</small>
    </Link>
  );
}

export function GoalsScreen() {
  const [formOpen, setFormOpen] = useState(false);
  const preview = usePreviewState();
  const { data, error, mutate } = useGoals();
  const revalidate = useRevalidateGoals();
  const goals = preview === "empty" ? [] : data;
  const openForm = () => setFormOpen(true);

  return (
    <AppShell>
      <div className="entity-page goals-page">
        <PageHeader
          title="Финансовые цели"
          description="Планируйте накопления и следите за прогрессом"
          actions={
            <button type="button" className="button primary" onClick={openForm}>
              Новая цель
            </button>
          }
        />
        {preview === "error" || error ? (
          <ErrorState error={error} retry={() => void mutate()} />
        ) : preview === "loading" || !goals ? (
          <div className="goal-grid" aria-busy="true">
            {[1, 2, 3].map((item) => (
              <SkeletonCard key={item} />
            ))}
          </div>
        ) : goals.length === 0 ? (
          <EmptyState
            title="Целей пока нет"
            description="Поставьте первую цель — мы рассчитаем, сколько откладывать в месяц"
            action={
              <button type="button" className="button primary" onClick={openForm}>
                Новая цель
              </button>
            }
          />
        ) : (
          <div className="goal-grid">
            {goals.map((goal) => (
              <GoalCard key={goal.id} goal={goal} />
            ))}
          </div>
        )}
        {formOpen && <GoalForm onClose={() => setFormOpen(false)} onSaved={revalidate} />}
      </div>
    </AppShell>
  );
}
