"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AppShell } from "@/components/app-shell";
import { ErrorState, PageHeader, SkeletonCard } from "@/components/common";
import { deleteDeposit } from "@/lib/api/client";
import { ApiError, toUserMessage } from "@/lib/api/errors";
import { useBanks, useDeposit } from "@/lib/api/hooks";
import { formatDate, formatMoney, formatPercent } from "@/lib/format";

import { DepositFormDialog, useRevalidateDeposits } from "./deposit-form";
import { Assumptions, DetailLine, MaturityFacts } from "./deposit-parts";
import {
  CAPITALIZATION_LABELS,
  DATA_ISSUE_LABELS,
  bankInitials,
  formatRateExact,
} from "./deposit-utils";
import { ConfirmDialog } from "@/components/confirm-dialog";

function DeleteDialog({ id, onCancel }: { id: number; onCancel: () => void }) {
  const router = useRouter();
  const revalidate = useRevalidateDeposits();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function remove() {
    setBusy(true);
    setError("");
    try {
      await deleteDeposit(id);
      await revalidate();
      router.push("/deposits");
    } catch (reason) {
      // Already deleted elsewhere: nothing left to delete, go back to the list.
      if (reason instanceof ApiError && reason.code === "deposit_not_found") {
        await revalidate();
        router.push("/deposits");
        return;
      }
      setError(toUserMessage(reason));
      setBusy(false);
    }
  }
  return (
    <ConfirmDialog
      title="Удалить депозит?"
      description={"Данные вклада будут удалены. Это действие нельзя отменить."}
      confirmLabel="Удалить"
      busyLabel="Удаление…"
      danger
      busy={busy}
      error={error || undefined}
      onConfirm={() => void remove()}
      onCancel={onCancel}
    />
  );
}

export function DepositDetail({ id }: { id: number }) {
  const validId = Number.isInteger(id) && id > 0;
  const { data: deposit, error, mutate } = useDeposit(validId ? id : null);
  const { data: banks } = useBanks();
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const back = (
    <Link href="/deposits" className="back-link">
      ← Все депозиты
    </Link>
  );
  if (!validId || error) {
    return (
      <div className="entity-page deposits-page">
        {back}
        <ErrorState
          title={!validId ? "Депозит не найден" : undefined}
          error={error}
          retry={validId ? () => void mutate() : undefined}
        />
      </div>
    );
  }
  if (!deposit) {
    return (
      <div className="entity-page deposits-page" aria-busy="true">
        {back}
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }
  const bank = banks?.find((item) => item.id === deposit.bank_id);
  const currency = deposit.currency_code;
  return (
    <div className="entity-page deposits-page">
      {back}
      <PageHeader
        title={bank?.name ?? "Депозит"}
        description={`${formatDate(deposit.start_date)} – ${formatDate(deposit.end_date)} · ${currency}`}
        actions={
          <>
            <button type="button" className="button secondary" onClick={() => setEditing(true)}>
              Изменить
            </button>
            <button type="button" className="button danger" onClick={() => setConfirmDelete(true)}>
              Удалить
            </button>
          </>
        }
      />
      <section className="deposit-detail-grid card-surface">
        <div className="deposit-detail-heading">
          <span className="bank-initials" aria-hidden="true">
            {bank ? bankInitials(bank.name) : "Б"}
          </span>
          <div>
            <strong>{formatMoney(deposit.principal, currency)}</strong>
            <span>{CAPITALIZATION_LABELS[deposit.capitalization]}</span>
          </div>
        </div>
        <div className="deposit-detail-list">
          <DetailLine label="Банк">{bank?.name ?? "—"}</DetailLine>
          <DetailLine label="Сумма">{formatMoney(deposit.principal, currency)}</DetailLine>
          <DetailLine label="Валюта">{currency}</DetailLine>
          <DetailLine label="Номинальная ставка">
            {formatPercent(deposit.interest_rate, true)}
          </DetailLine>
          <DetailLine label="ГЭСВ (по данным банка)">
            {deposit.effective_rate === null ? (
              <span title="Банк не указал ГЭСВ">—</span>
            ) : (
              formatRateExact(deposit.effective_rate)
            )}
          </DetailLine>
          <DetailLine label="Капитализация">
            {CAPITALIZATION_LABELS[deposit.capitalization]}
          </DetailLine>
          <DetailLine label="Дата начала">{formatDate(deposit.start_date)}</DetailLine>
          <DetailLine label="Дата окончания">{formatDate(deposit.end_date)}</DetailLine>
        </div>
      </section>
      <section className="entity-section card-surface deposit-calculation-detail">
        <header>
          <h2>Расчёт к концу срока</h2>
          <p>Оценка; расчёт банка может отличаться</p>
        </header>
        {deposit.maturity ? (
          <>
            <MaturityFacts maturity={deposit.maturity} currency={currency} />
            <Assumptions items={deposit.maturity.assumptions} />
          </>
        ) : (
          <p className="deposit-data-issue" role="status">
            Расчёт недоступен:{" "}
            {deposit.data_issue ? DATA_ISSUE_LABELS[deposit.data_issue] : "некорректные данные."}{" "}
            Исправьте даты вклада — до этого он не учитывается в итогах.
          </p>
        )}
      </section>
      {editing && <DepositFormDialog deposit={deposit} onClose={() => setEditing(false)} />}
      {confirmDelete && <DeleteDialog id={id} onCancel={() => setConfirmDelete(false)} />}
    </div>
  );
}

export function DepositDetailScreen({ id }: { id: number }) {
  return (
    <AppShell>
      <DepositDetail id={id} />
    </AppShell>
  );
}
