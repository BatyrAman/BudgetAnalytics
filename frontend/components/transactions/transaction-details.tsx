"use client";

import { useId, useState } from "react";
import { useSWRConfig } from "swr";
import { toast } from "sonner";
import { X } from "lucide-react";

import { EmptyState, ErrorState, Skeleton } from "@/components/common";
import { deleteTransaction } from "@/lib/api/client";
import { ApiError, toUserMessage } from "@/lib/api/errors";
import { useAccounts, useTransaction } from "@/lib/api/hooks";
import { formatDateTime, formatMoney, signForType } from "@/lib/format";
import type { Transaction } from "@/lib/types";

import { ConfirmDialog } from "./confirm-dialog";
import { TYPE_LABELS } from "./filters";
import { revalidateTransactionData } from "./revalidate";

function Sheet({
  labelledBy,
  label,
  onClose,
  children,
}: {
  labelledBy?: string;
  label?: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      className="sheet-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape") onClose();
      }}
    >
      <section
        className="transaction-details overlay-shadow"
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        aria-label={label}
      >
        {children}
      </section>
    </div>
  );
}

/** T-2: details drawer for one transaction with edit and delete actions. */
export function TransactionDetails({
  id,
  onClose,
  onEdit,
  onDeleted,
}: {
  id: number;
  onClose: () => void;
  onEdit: (transaction: Transaction) => void;
  onDeleted: () => void;
}) {
  const titleId = useId();
  const { mutate: globalMutate } = useSWRConfig();
  const { data: transaction, error, isLoading, mutate } = useTransaction(id);
  const { data: accounts } = useAccounts(true);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  const closeButton = (
    <button type="button" className="icon-button" aria-label="Закрыть" onClick={onClose}>
      <X />
    </button>
  );

  if (error) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <Sheet label="Детали операции" onClose={onClose}>
        {closeButton}
        {notFound ? (
          <EmptyState title="Операция не найдена" description="Возможно, она была удалена." />
        ) : (
          <ErrorState error={error} retry={() => void mutate()} />
        )}
      </Sheet>
    );
  }
  if (isLoading || !transaction) {
    return (
      <Sheet label="Загрузка операции" onClose={onClose}>
        {closeButton}
        <Skeleton className="large" />
        <Skeleton className="medium" />
        <Skeleton className="medium" />
      </Sheet>
    );
  }

  const sign = signForType(transaction.transaction_type);
  const account = accounts?.find((item) => item.id === transaction.account_id);

  async function remove() {
    if (!transaction) return;
    setDeleting(true);
    setDeleteError("");
    try {
      await deleteTransaction(transaction.id);
      toast.success("Операция удалена");
      void globalMutate(["transaction", transaction.id], undefined, { revalidate: false });
      void revalidateTransactionData(globalMutate, transaction.id);
      onDeleted();
    } catch (failure) {
      setDeleteError(toUserMessage(failure));
      setDeleting(false);
    }
  }

  return (
    <Sheet labelledBy={titleId} onClose={onClose}>
      <header className="overlay-heading">
        <div>
          <h2 id={titleId}>Детали операции</h2>
          <p>{TYPE_LABELS[transaction.transaction_type]}</p>
        </div>
        {closeButton}
      </header>
      <strong className={`detail-amount tabular-nums ${sign === "+" ? "text-positive" : ""}`}>
        {formatMoney(transaction.amount, transaction.currency_code, { sign })}
      </strong>
      <dl className="detail-list">
        <div>
          <dt>Дата и время</dt>
          <dd>{formatDateTime(transaction.transaction_date)}</dd>
        </div>
        <div>
          <dt>Категория</dt>
          <dd>{transaction.category_name || "—"}</dd>
        </div>
        <div>
          <dt>Счёт</dt>
          <dd>
            {transaction.account_id === null
              ? "—"
              : account
                ? `${account.name}${account.is_archived ? " (архив)" : ""}`
                : "…"}
          </dd>
        </div>
        <div>
          <dt>Банк</dt>
          <dd>{transaction.bank_name || "—"}</dd>
        </div>
        <div>
          <dt>Описание</dt>
          <dd>{transaction.description || "—"}</dd>
        </div>
        <div>
          <dt>Создано</dt>
          <dd>{formatDateTime(transaction.created_at)}</dd>
        </div>
        <div>
          <dt>Изменено</dt>
          <dd>{formatDateTime(transaction.updated_at)}</dd>
        </div>
      </dl>
      <footer className="dialog-actions">
        <button type="button" className="button secondary" onClick={() => onEdit(transaction)}>
          Редактировать
        </button>
        <button type="button" className="button danger" onClick={() => setConfirmDelete(true)}>
          Удалить
        </button>
      </footer>
      {confirmDelete && (
        <ConfirmDialog
          title="Удалить операцию?"
          description={`Удалить операцию на ${formatMoney(transaction.amount, transaction.currency_code)}? Действие нельзя отменить.`}
          confirmLabel={deleting ? "Удаляем…" : "Удалить"}
          danger
          busy={deleting}
          error={deleteError}
          onConfirm={() => void remove()}
          onCancel={() => {
            setConfirmDelete(false);
            setDeleteError("");
          }}
        />
      )}
    </Sheet>
  );
}
