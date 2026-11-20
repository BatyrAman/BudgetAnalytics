"use client";

import { useState } from "react";

import { createBudget, updateBudget, type BudgetInput } from "@/lib/api/client";
import { ApiError, toUserMessage } from "@/lib/api/errors";
import { useCategories, useDefaultCurrency } from "@/lib/api/hooks";
import { parseAmountInput } from "@/lib/format";
import type { Budget } from "@/lib/types";

import "./budgets.css";

type FieldName = "title" | "monthly_limit" | "currency" | "category_id";
type Errors = Partial<Record<FieldName | "form", string>>;

const FIELD_NAMES: FieldName[] = ["title", "monthly_limit", "currency", "category_id"];
/** No currency list endpoint (G-5): static picker list. */
const CURRENCIES = ["KZT", "USD", "EUR", "RUB"];
const AMOUNT = /^\d{1,16}(\.\d{1,2})?$/;

export function budgetErrors(error: unknown): Errors {
  if (!(error instanceof ApiError)) return { form: toUserMessage(error) };
  if (error.code === "budget_income_category" || error.code === "category_not_found") {
    return { category_id: toUserMessage(error) };
  }
  if (error.code === "unknown_currency") return { currency: toUserMessage(error) };
  const errors: Errors = {};
  for (const item of error.fieldErrors) {
    const field = FIELD_NAMES.find((name) => name === item.field);
    if (field) errors[field] = item.message;
  }
  if (Object.keys(errors).length === 0) errors.form = toUserMessage(error);
  return errors;
}

function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <small id={id} className="field-error" role="alert">
      {message}
    </small>
  );
}

export function BudgetForm({
  budget,
  onClose,
  onSaved,
}: {
  budget?: Budget;
  onClose: () => void;
  onSaved: (budget: Budget) => Promise<unknown> | void;
}) {
  const defaultCurrency = useDefaultCurrency();
  const { data: categories, error: categoriesError } = useCategories("expense");
  const [title, setTitle] = useState(budget?.title ?? "");
  const [limit, setLimit] = useState(budget?.monthly_limit ?? "");
  const [currency, setCurrency] = useState<string | null>(budget?.currency_code ?? null);
  const [categoryId, setCategoryId] = useState(
    budget?.category_id ? String(budget.category_id) : "",
  );
  const [errors, setErrors] = useState<Errors>({});
  const [busy, setBusy] = useState(false);

  const selectedCurrency = currency ?? defaultCurrency;
  const currencyOptions = Array.from(new Set([selectedCurrency, defaultCurrency, ...CURRENCIES]));

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = title.trim();
    const amount = parseAmountInput(limit);
    const next: Errors = {};
    if (trimmed.length < 2 || trimmed.length > 100) {
      next.title = "Название должно содержать от 2 до 100 символов.";
    }
    if (!AMOUNT.test(amount) || !/[1-9]/.test(amount)) {
      next.monthly_limit = "Лимит должен быть числом больше нуля (до 2 знаков после запятой).";
    }
    if (Object.keys(next).length > 0) {
      setErrors(next);
      return;
    }
    const input: BudgetInput = {
      title: trimmed,
      monthly_limit: amount,
      currency: selectedCurrency,
      category_id: categoryId ? Number(categoryId) : null,
    };
    setBusy(true);
    setErrors({});
    try {
      const saved = budget ? await updateBudget(budget.id, input) : await createBudget(input);
      await onSaved(saved);
      onClose();
    } catch (error) {
      setErrors(budgetErrors(error));
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
        className="demo-dialog budget-form-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="budget-form-title"
      >
        <button type="button" className="dialog-close" onClick={onClose} aria-label="Закрыть">
          ×
        </button>
        <h2 id="budget-form-title">{budget ? "Изменить бюджет" : "Создать бюджет"}</h2>
        <form className="entity-form" onSubmit={submit} noValidate>
          <label className="field-label">
            Название *
            <input
              name="title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              maxLength={100}
              aria-invalid={Boolean(errors.title)}
              aria-describedby={errors.title ? "budget-title-error" : undefined}
              autoFocus
            />
            <FieldError id="budget-title-error" message={errors.title} />
          </label>
          <label className="field-label">
            Месячный лимит *
            <input
              name="monthly_limit"
              type="text"
              inputMode="decimal"
              autoComplete="off"
              value={limit}
              onChange={(event) => setLimit(event.target.value)}
              aria-invalid={Boolean(errors.monthly_limit)}
              aria-describedby={errors.monthly_limit ? "budget-limit-error" : undefined}
            />
            <FieldError id="budget-limit-error" message={errors.monthly_limit} />
          </label>
          <div className="form-two">
            <label className="field-label">
              Валюта
              <select
                name="currency"
                value={selectedCurrency}
                onChange={(event) => setCurrency(event.target.value)}
                aria-invalid={Boolean(errors.currency)}
              >
                {currencyOptions.map((code) => (
                  <option key={code} value={code}>
                    {code}
                  </option>
                ))}
              </select>
              <FieldError id="budget-currency-error" message={errors.currency} />
            </label>
            <label className="field-label">
              Категория
              <select
                name="category_id"
                value={categoryId}
                onChange={(event) => setCategoryId(event.target.value)}
                aria-invalid={Boolean(errors.category_id)}
                aria-describedby={errors.category_id ? "budget-category-error" : undefined}
              >
                <option value="">Все расходы</option>
                {(categories ?? []).map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                    {category.kind === "any" ? " · Любой тип" : ""}
                  </option>
                ))}
              </select>
              {categoriesError && !errors.category_id && (
                <small className="field-error">Не удалось загрузить категории.</small>
              )}
              <FieldError id="budget-category-error" message={errors.category_id} />
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
              {busy ? "Сохранение…" : "Сохранить бюджет"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
