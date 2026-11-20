"use client";

import { useState } from "react";
import { deleteAccount } from "@/lib/api/client";
import { ApiError, toUserMessage } from "@/lib/api/errors";

/**
 * Delete confirmation. The backend decides whether deletion is allowed: on
 * 409 `account_has_transactions` the dialog offers archiving instead.
 */
export function DeleteAccountDialog({
  accountId,
  isArchived,
  onClose,
  onDeleted,
  onArchive,
}: {
  accountId: number;
  isArchived: boolean;
  onClose: () => void;
  onDeleted: () => Promise<void> | void;
  onArchive: () => Promise<void>;
}) {
  const [blocked, setBlocked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function remove() {
    setBusy(true);
    setError("");
    try {
      await deleteAccount(accountId);
      await onDeleted();
    } catch (failure) {
      if (failure instanceof ApiError && failure.code === "account_has_transactions") {
        setBlocked(true);
      } else {
        setError(toUserMessage(failure));
      }
    } finally {
      setBusy(false);
    }
  }

  async function archive() {
    setBusy(true);
    setError("");
    try {
      await onArchive();
    } catch (failure) {
      setError(toUserMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="overlay-backdrop" onKeyDown={(event) => event.key === "Escape" && onClose()}>
      <section
        className="demo-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="delete-account-title"
        aria-describedby="delete-account-text"
      >
        <h2 id="delete-account-title">{blocked ? "Удалить счёт нельзя" : "Удалить счёт?"}</h2>
        <p id="delete-account-text">
          {blocked
            ? isArchived
              ? "На счёте есть операции, поэтому удалить его нельзя. Счёт уже в архиве."
              : "На счёте есть операции, поэтому удалить его нельзя. Архивируйте счёт — он скроется из списков, а история сохранится."
            : "Это действие нельзя отменить."}
        </p>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <div className="dialog-actions">
          <button type="button" className="button secondary" onClick={onClose} autoFocus>
            Отмена
          </button>
          {blocked ? (
            !isArchived && (
              <button
                type="button"
                className="button primary"
                disabled={busy}
                onClick={() => void archive()}
              >
                Архивировать
              </button>
            )
          ) : (
            <button
              type="button"
              className="button danger"
              disabled={busy}
              onClick={() => void remove()}
            >
              {busy ? "Удаление…" : "Удалить"}
            </button>
          )}
        </div>
      </section>
    </div>
  );
}
