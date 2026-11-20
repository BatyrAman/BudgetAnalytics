"use client";

import { useState } from "react";
import { useSWRConfig } from "swr";

import { createGoal, updateGoal, type GoalInput } from "@/lib/api/client";
import { ApiError, toUserMessage } from "@/lib/api/errors";
import { useDefaultCurrency } from "@/lib/api/hooks";
import { parseAmountInput } from "@/lib/format";
import type { Goal } from "@/lib/types";

import "./goals.css";

type FieldName = "name" | "target_amount" | "saved_amount" | "currency" | "target_date";
type Errors = Partial<Record<FieldName | "form", string>>;

const FIELD_NAMES: FieldName[] = [
  "name",
  "target_amount",
  "saved_amount",
  "currency",
  "target_date",
];
/** No currency list endpoint (G-5): static picker list. */
const CURRENCIES = ["KZT", "USD", "EUR", "RUB"];
const AMOUNT = /^\d{1,16}(\.\d{1,2})?$/;

export const isAmount = (value: string) => AMOUNT.test(value);
export const isPositiveAmount = (value: string) => AMOUNT.test(value) && /[1-9]/.test(value);

/** Revalidate goal list and details after a mutation. */
export function useRevalidateGoals() {
  const { mutate } = useSWRConfig();
  return () => mutate((key) => Array.isArray(key) && (key[0] === "goals" || key[0] === "goal"));
}

export function goalErrors(error: unknown): Errors {
  if (!(error instanceof ApiError)) return { form: toUserMessage(error) };
  if (error.code === "goal_name_taken") return { name: toUserMessage(error) };
  if (error.code === "unknown_currency") return { currency: toUserMessage(error) };
  const errors: Errors = {};
  for (const item of error.fieldErrors) {
    const field = FIELD_NAMES.find((name) => name === item.field);
    if (field) errors[field] = item.message;
  }
  if (Object.keys(errors).length === 0) errors.form = toUserMessage(error);
  return errors;
}

export function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <small id={id} className="field-error" role="alert">
      {message}
    </small>
  );
}

export function GoalForm({
  goal,
  onClose,
  onSaved,
}: {
  goal?: Goal;
  onClose: () => void;
  onSaved: () => Promise<unknown> | void;
}) {
  const defaultCurrency = useDefaultCurrency();
  const [name, setName] = useState(goal?.name ?? "");
  const [target, setTarget] = useState(goal?.target_amount ?? "");
  const [saved, setSaved] = useState("0");
  const [currency, setCurrency] = useState<string | null>(null);
  const [targetDate, setTargetDate] = useState(goal?.target_date ?? "");
  const [errors, setErrors] = useState<Errors>({});
  const [busy, setBusy] = useState(false);
  const selectedCurrency = goal?.currency_code ?? currency ?? defaultCurrency;
  const currencyOptions = Array.from(new Set([selectedCurrency, defaultCurrency, ...CURRENCIES]));

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = name.trim();
    const targetAmount = parseAmountInput(target);
    const savedAmount = parseAmountInput(saved);
    const next: Errors = {};
    if (trimmed.length < 1 || trimmed.length > 100) {
      next.name = "Название должно содержать от 1 до 100 символов.";
    }
    if (!isPositiveAmount(targetAmount)) {
      next.target_amount = "Целевая сумма должна быть больше нуля.";
    }
    if (!goal && !isAmount(savedAmount)) {
      next.saved_amount = "Укажите сумму не меньше нуля.";
    }
    if (Object.keys(next).length > 0) {
      setErrors(next);
      return;
    }
    setBusy(true);
    setErrors({});
    try {
      if (goal) {
        await updateGoal(goal.id, {
          name: trimmed,
          target_amount: targetAmount,
          target_date: targetDate || null,
        });
      } else {
        const input: GoalInput = {
          name: trimmed,
          target_amount: targetAmount,
          saved_amount: savedAmount,
          currency: selectedCurrency,
          target_date: targetDate || null,
        };
        await createGoal(input);
      }
      await onSaved();
      onClose();
    } catch (error) {
      setErrors(goalErrors(error));
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
        className="demo-dialog goal-form-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="goal-form-title"
      >
        <button type="button" className="dialog-close" onClick={onClose} aria-label="Закрыть">
          ×
        </button>
        <h2 id="goal-form-title">{goal ? "Изменить цель" : "Новая цель"}</h2>
        <form className="entity-form" onSubmit={submit} noValidate>
          <label className="field-label">
            Название *
            <input
              name="name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={100}
              aria-invalid={Boolean(errors.name)}
              aria-describedby={errors.name ? "goal-name-error" : undefined}
              autoFocus
            />
            <FieldError id="goal-name-error" message={errors.name} />
          </label>
          <div className="form-two">
            <label className="field-label">
              Целевая сумма *
              <input
                name="target_amount"
                type="text"
                inputMode="decimal"
                autoComplete="off"
                value={target}
                onChange={(event) => setTarget(event.target.value)}
                aria-invalid={Boolean(errors.target_amount)}
                aria-describedby={errors.target_amount ? "goal-target-error" : undefined}
              />
              <FieldError id="goal-target-error" message={errors.target_amount} />
            </label>
            {goal ? (
              <p className="goal-savings-note">
                Накопления меняются кнопкой «Обновить накопления».
              </p>
            ) : (
              <label className="field-label">
                Уже накоплено
                <input
                  name="saved_amount"
                  type="text"
                  inputMode="decimal"
                  autoComplete="off"
                  value={saved}
                  onChange={(event) => setSaved(event.target.value)}
                  aria-invalid={Boolean(errors.saved_amount)}
                  aria-describedby={errors.saved_amount ? "goal-saved-error" : undefined}
                />
                <FieldError id="goal-saved-error" message={errors.saved_amount} />
              </label>
            )}
          </div>
          <div className="form-two">
            <label className="field-label">
              Валюта
              <select
                name="currency"
                value={selectedCurrency}
                onChange={(event) => setCurrency(event.target.value)}
                disabled={Boolean(goal)}
                aria-describedby={goal ? "goal-currency-locked" : undefined}
              >
                {currencyOptions.map((code) => (
                  <option key={code} value={code}>
                    {code}
                  </option>
                ))}
              </select>
              {goal && (
                <small id="goal-currency-locked" className="goal-savings-note">
                  Валюту цели нельзя изменить
                </small>
              )}
              <FieldError id="goal-currency-error" message={errors.currency} />
            </label>
            <label className="field-label">
              Целевая дата
              <input
                name="target_date"
                type="date"
                value={targetDate}
                onChange={(event) => setTargetDate(event.target.value)}
                aria-invalid={Boolean(errors.target_date)}
              />
              <FieldError id="goal-date-error" message={errors.target_date} />
            </label>
          </div>
          {errors.form && (
            <p className="form-error" role="alert">
              {errors.form}
            </p>
          )}
          <div className="dialog-actions">
            <button type="button" className="button secondary" onClick={onClose}>
              Отмена
            </button>
            <button type="submit" className="button primary" disabled={busy}>
              {busy ? "Сохранение…" : "Сохранить цель"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
