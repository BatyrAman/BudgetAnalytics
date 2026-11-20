"use client";

import { useState } from "react";

import { updateGoal } from "@/lib/api/client";
import { formatMoney, parseAmountInput } from "@/lib/format";
import type { Goal } from "@/lib/types";

import { FieldError, goalErrors, isAmount } from "./goal-form";
import "./goals.css";

/** «Обновить накопления»: sends the NEW TOTAL saved amount (not a delta) as a string. */
export function SavingsForm({
  goal,
  onClose,
  onSaved,
}: {
  goal: Goal;
  onClose: () => void;
  onSaved: () => Promise<unknown> | void;
}) {
  const [value, setValue] = useState(goal.saved_amount);
  const [error, setError] = useState<{ field?: string; form?: string }>({});
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const amount = parseAmountInput(value);
    if (!isAmount(amount)) {
      setError({ field: "Укажите сумму не меньше нуля." });
      return;
    }
    setBusy(true);
    setError({});
    try {
      await updateGoal(goal.id, { saved_amount: amount });
      await onSaved();
      onClose();
    } catch (reason) {
      const mapped = goalErrors(reason);
      setError({ field: mapped.saved_amount, form: mapped.form ?? mapped.name });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="overlay-backdrop"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <section
        className="demo-dialog goal-savings-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="savings-form-title"
      >
        <button type="button" className="dialog-close" onClick={onClose} aria-label="Закрыть">
          ×
        </button>
        <h2 id="savings-form-title">Обновить накопления</h2>
        <form className="entity-form" onSubmit={submit} noValidate>
          <label className="field-label">
            Сейчас накоплено, {goal.currency_code}
            <input
              name="saved_amount"
              type="text"
              inputMode="decimal"
              autoComplete="off"
              value={value}
              onChange={(event) => setValue(event.target.value)}
              aria-invalid={Boolean(error.field)}
              aria-describedby="savings-hint"
              autoFocus
            />
            <FieldError id="savings-error" message={error.field} />
          </label>
          <small id="savings-hint" className="goal-savings-note">
            Укажите, сколько всего накоплено на цель сейчас (не сумму пополнения). Было:{" "}
            {formatMoney(goal.saved_amount, goal.currency_code)}.
          </small>
          {error.form && (
            <p className="form-error" role="alert">
              {error.form}
            </p>
          )}
          <div className="dialog-actions">
            <button type="button" className="button secondary" onClick={onClose}>
              Отмена
            </button>
            <button type="submit" className="button primary" disabled={busy}>
              {busy ? "Обновление…" : "Обновить"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
