"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AppShell } from "@/components/app-shell";
import { ErrorState, PageHeader, SkeletonCard } from "@/components/common";
import { deleteGoal } from "@/lib/api/client";
import { toUserMessage } from "@/lib/api/errors";
import { useGoal } from "@/lib/api/hooks";
import { formatDate, formatMoney, formatPercent } from "@/lib/format";
import type { Goal } from "@/lib/types";

import { GoalForm, useRevalidateGoals } from "./goal-form";
import { GoalProgress, MonthlySaving, MonthsLeft, ReachedBadge } from "./goals-screen";
import { SavingsForm } from "./savings-form";
import "./goals.css";
import { ConfirmDialog } from "@/components/confirm-dialog";

function DeleteGoalDialog({
  goal,
  onClose,
  onDeleted,
}: {
  goal: Goal;
  onClose: () => void;
  onDeleted: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function confirm() {
    setBusy(true);
    setError("");
    try {
      await deleteGoal(goal.id);
      await onDeleted();
    } catch (reason) {
      setError(toUserMessage(reason));
      setBusy(false);
    }
  }
  return (
    <ConfirmDialog
      title="Удалить цель?"
      description={<>Цель «{goal.name}» будет удалена.</>}
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

export function GoalDetailScreen({ id }: { id: number }) {
  const router = useRouter();
  const [dialog, setDialog] = useState<"edit" | "savings" | "delete" | null>(null);
  const { data: goal, error, mutate } = useGoal(id);
  const revalidate = useRevalidateGoals();
  const close = () => setDialog(null);

  let content: React.ReactNode;
  if (error) {
    content = <ErrorState error={error} retry={() => void mutate()} />;
  } else if (!goal) {
    content = <SkeletonCard />;
  } else {
    content = (
      <>
        <PageHeader
          title={goal.name}
          description={
            goal.target_date ? `Целевая дата: ${formatDate(goal.target_date)}` : "Без срока"
          }
          actions={goal.is_reached ? <ReachedBadge /> : undefined}
        />
        <div className="goal-detail-actions">
          <button type="button" className="button primary" onClick={() => setDialog("savings")}>
            Обновить накопления
          </button>
          <button type="button" className="button secondary" onClick={() => setDialog("edit")}>
            Изменить
          </button>
          <button type="button" className="button danger" onClick={() => setDialog("delete")}>
            Удалить
          </button>
        </div>
        <section className="goal-detail-progress card-surface">
          <div className="goal-card-top">
            <span>
              Накоплено {formatMoney(goal.saved_amount, goal.currency_code)} из{" "}
              {formatMoney(goal.target_amount, goal.currency_code)}
            </span>
            <strong>{formatPercent(goal.progress_percent)}</strong>
          </div>
          <GoalProgress goal={goal} />
          <span>Осталось: {formatMoney(goal.remaining, goal.currency_code)}</span>
        </section>
        <section className="goal-detail-grid">
          <article className="budget-metric card-surface">
            <span>Целевая сумма</span>
            <strong>{formatMoney(goal.target_amount, goal.currency_code)}</strong>
          </article>
          <article className="budget-metric card-surface">
            <span>Сейчас накоплено</span>
            <strong>{formatMoney(goal.saved_amount, goal.currency_code)}</strong>
          </article>
          <article className="budget-metric card-surface">
            <span>Месяцев до срока</span>
            <strong>
              <MonthsLeft goal={goal} />
            </strong>
          </article>
          <article className="budget-metric card-surface">
            <span>Нужно откладывать</span>
            <strong>
              <MonthlySaving goal={goal} />
            </strong>
          </article>
        </section>
        <p className="goal-savings-note">Накопления вводятся вручную и не связаны со счетами.</p>
        <p className="goal-savings-note">Равными частями, без учёта процентов.</p>
        {dialog === "edit" && <GoalForm goal={goal} onClose={close} onSaved={revalidate} />}
        {dialog === "savings" && <SavingsForm goal={goal} onClose={close} onSaved={revalidate} />}
        {dialog === "delete" && (
          <DeleteGoalDialog
            goal={goal}
            onClose={close}
            onDeleted={async () => {
              router.push("/goals");
              await revalidate();
            }}
          />
        )}
      </>
    );
  }

  return (
    <AppShell>
      <div className="entity-page goal-detail-page">
        <Link href="/goals" className="back-link">
          ← Все цели
        </Link>
        {content}
      </div>
    </AppShell>
  );
}
