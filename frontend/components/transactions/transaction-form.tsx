"use client";

import { useId, useMemo, useState } from "react";
import { useSWRConfig } from "swr";
import { toast } from "sonner";
import { X } from "lucide-react";

import {
  createTransaction,
  currentTimezone,
  updateTransaction,
  type TransactionInput,
} from "@/lib/api/client";
import { ApiError, toUserMessage } from "@/lib/api/errors";
import { useAccounts, useBanks, useCategories, useDefaultCurrency } from "@/lib/api/hooks";
import { parseAmountInput } from "@/lib/format";
import type { Transaction, TransactionType } from "@/lib/types";

import { ConfirmDialog } from "./confirm-dialog";
import { CURRENCY_CHOICES, TRANSACTION_TYPES, TYPE_LABELS, isCategoryAllowed } from "./filters";
import { fromLocalDateTimeInput, toLocalDateTimeInput } from "./period";
import { revalidateTransactionData } from "./revalidate";
import "./transactions.css";

type FieldKey =
  | "transaction_type"
  | "amount"
  | "transaction_date"
  | "category_id"
  | "account_id"
  | "currency"
  | "bank_id"
  | "description";
type FieldErrors = Partial<Record<FieldKey, string>>;

const FIELD_KEYS: FieldKey[] = [
  "transaction_type",
  "amount",
  "transaction_date",
  "category_id",
  "account_id",
  "currency",
  "bank_id",
  "description",
];

/** Backend business codes that belong to a specific field. */
const CODE_FIELDS: Record<string, FieldKey> = {
  category_kind_mismatch: "category_id",
  category_not_found: "category_id",
  currency_mismatch: "currency",
  unknown_currency: "currency",
  account_not_found: "account_id",
  bank_not_found: "bank_id",
};

const AMOUNT_RE = /^\d{1,16}(\.\d{1,2})?$/;

export type TransactionFormDefaults = {
  transaction_type?: TransactionType;
  account_id?: number;
  category_id?: number;
};

type FormValues = {
  type: TransactionType;
  amount: string;
  when: string;
  categoryId: string;
  accountId: string;
  currency: string | null; // null = user's default currency (until chosen)
  bankId: string;
  description: string;
};

function initialValues(
  transaction: Transaction | undefined,
  defaults: TransactionFormDefaults,
  timeZone: string,
): FormValues {
  return {
    type: transaction?.transaction_type ?? defaults.transaction_type ?? "expense",
    amount: transaction?.amount ?? "",
    when: toLocalDateTimeInput(transaction?.transaction_date ?? new Date().toISOString(), timeZone),
    categoryId: String(transaction?.category_id ?? defaults.category_id ?? ""),
    accountId: String(transaction?.account_id ?? defaults.account_id ?? ""),
    currency: transaction?.currency_code ?? null,
    bankId: String(transaction?.bank_id ?? ""),
    description: transaction?.description ?? "",
  };
}

/**
 * T-3: create (no `transaction`) or edit a transaction. Categories are filtered by
 * type, archived accounts are hidden, the currency follows the chosen account.
 */
export function TransactionForm({
  transaction,
  defaults = {},
  onClose,
  onSaved,
}: {
  transaction?: Transaction;
  defaults?: TransactionFormDefaults;
  onClose: () => void;
  onSaved: (saved: Transaction) => void;
}) {
  const { mutate } = useSWRConfig();
  const [timeZone] = useState(currentTimezone);
  const [initial] = useState(() => initialValues(transaction, defaults, timeZone));
  const [values, setValues] = useState<FormValues>(initial);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const ids = useId();

  const categoriesQuery = useCategories();
  const accountsQuery = useAccounts(true);
  const banksQuery = useBanks();
  const defaultCurrency = useDefaultCurrency();
  const categories = useMemo(() => categoriesQuery.data ?? [], [categoriesQuery.data]);
  const accounts = useMemo(() => accountsQuery.data ?? [], [accountsQuery.data]);
  const banks = banksQuery.data ?? [];

  const allowedCategories = categories.filter((category) =>
    isCategoryAllowed(category, values.type),
  );
  // Archived accounts are hidden (backend does not block them — G-9), except the one already set.
  const selectableAccounts = accounts.filter(
    (account) => !account.is_archived || String(account.id) === initial.accountId,
  );
  const selectedAccount = accounts.find((account) => String(account.id) === values.accountId);
  const currency = selectedAccount?.currency_code ?? values.currency ?? defaultCurrency;
  const currencyOptions = Array.from(
    new Set([
      defaultCurrency,
      ...CURRENCY_CHOICES,
      ...accounts.filter((a) => !a.is_archived).map((a) => a.currency_code),
      currency,
    ]),
  );

  const dirty = (Object.keys(initial) as (keyof FormValues)[]).some(
    (key) => initial[key] !== values[key],
  );

  function set<K extends keyof FormValues>(key: K, value: FormValues[K], field?: FieldKey) {
    setValues((current) => ({ ...current, [key]: value }));
    if (field) setErrors((current) => ({ ...current, [field]: undefined }));
  }

  function changeType(type: TransactionType) {
    setValues((current) => {
      const category = categories.find((item) => String(item.id) === current.categoryId);
      const keep = category ? isCategoryAllowed(category, type) : false;
      return { ...current, type, categoryId: keep ? current.categoryId : "" };
    });
    setErrors((current) => ({ ...current, transaction_type: undefined, category_id: undefined }));
  }

  function requestClose() {
    if (saving) return;
    if (dirty) setConfirmDiscard(true);
    else onClose();
  }

  function validate(): { errors: FieldErrors; date: string | null } {
    const next: FieldErrors = {};
    if (!values.amount) next.amount = "Укажите сумму.";
    else if (!AMOUNT_RE.test(values.amount)) next.amount = "Не больше 2 знаков после запятой.";
    else if (!/[1-9]/.test(values.amount)) next.amount = "Сумма должна быть больше нуля.";
    const date = fromLocalDateTimeInput(values.when, timeZone);
    if (!date) next.transaction_date = "Укажите дату и время.";
    if (!values.categoryId) next.category_id = "Выберите категорию.";
    else if (!allowedCategories.some((category) => String(category.id) === values.categoryId))
      next.category_id = "Категория не подходит для этого типа операции.";
    if (values.description.length > 500) next.description = "Не больше 500 символов.";
    return { errors: next, date };
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const checked = validate();
    setErrors(checked.errors);
    setFormError("");
    if (Object.keys(checked.errors).length > 0 || !checked.date) return;
    const payload: TransactionInput = {
      amount: values.amount,
      transaction_type: values.type,
      transaction_date: checked.date,
      category_id: Number(values.categoryId),
      description: values.description.trim() || null,
      account_id: values.accountId ? Number(values.accountId) : null,
      bank_id: values.bankId ? Number(values.bankId) : null,
      currency,
    };
    setSaving(true);
    try {
      const saved = transaction
        ? await updateTransaction(transaction.id, payload)
        : await createTransaction(payload);
      toast.success(transaction ? "Операция сохранена" : "Операция добавлена");
      void revalidateTransactionData(mutate);
      onSaved(saved);
    } catch (error) {
      applyServerError(error);
    } finally {
      setSaving(false);
    }
  }

  function applyServerError(error: unknown) {
    if (error instanceof ApiError) {
      const field = CODE_FIELDS[error.code];
      if (field) {
        setErrors({ [field]: toUserMessage(error) });
        return;
      }
      if (error.fieldErrors.length > 0) {
        const mapped: FieldErrors = {};
        let unmapped = false;
        for (const issue of error.fieldErrors) {
          const key = FIELD_KEYS.find((candidate) => candidate === issue.field);
          if (key) mapped[key] ??= issue.message;
          else unmapped = true;
        }
        setErrors(mapped);
        if (unmapped || Object.keys(mapped).length === 0) setFormError(toUserMessage(error));
        return;
      }
    }
    setFormError(toUserMessage(error));
  }

  const fieldProps = (field: FieldKey) => ({
    "aria-invalid": errors[field] ? true : undefined,
    "aria-describedby": errors[field] ? `${ids}-${field}-error` : undefined,
  });
  const fieldError = (field: FieldKey) =>
    errors[field] ? (
      <span className="transactions-field-error" id={`${ids}-${field}-error`} role="alert">
        {errors[field]}
      </span>
    ) : null;

  const referenceError = categoriesQuery.error ?? accountsQuery.error ?? banksQuery.error;

  return (
    <div
      className="overlay-backdrop transaction-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) requestClose();
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape" && !confirmDiscard) requestClose();
      }}
    >
      <section
        className="transaction-form-dialog overlay-shadow"
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${ids}-title`}
      >
        <header className="overlay-heading">
          <div>
            <h2 id={`${ids}-title`}>
              {transaction ? "Редактировать операцию" : "Добавить операцию"}
            </h2>
            <p>Заполните данные операции</p>
          </div>
          <button type="button" className="icon-button" aria-label="Закрыть" onClick={requestClose}>
            <X />
          </button>
        </header>
        <form onSubmit={submit} noValidate>
          <fieldset className="field-label transactions-type-fieldset">
            <legend>Тип операции</legend>
            <div className="segmented transaction-types">
              {TRANSACTION_TYPES.map((type) => (
                <button
                  type="button"
                  className={values.type === type ? "selected" : ""}
                  aria-pressed={values.type === type}
                  key={type}
                  onClick={() => changeType(type)}
                >
                  {TYPE_LABELS[type]}
                </button>
              ))}
            </div>
            {fieldError("transaction_type")}
          </fieldset>
          {(values.type === "transfer_in" || values.type === "transfer_out") && (
            <p className="field-hint">
              Перевод между своими счетами — это две операции: списание с одного счёта и поступление
              на другой.
            </p>
          )}
          <div className="form-grid">
            <label className="field-label">
              Сумма *
              <span className="amount-field">
                <input
                  inputMode="decimal"
                  autoComplete="off"
                  value={values.amount}
                  onChange={(event) =>
                    set("amount", parseAmountInput(event.target.value), "amount")
                  }
                  placeholder="0,00"
                  {...fieldProps("amount")}
                />
                <b aria-hidden="true">{currency}</b>
              </span>
              {fieldError("amount")}
            </label>
            <label className="field-label">
              Дата и время *
              <input
                type="datetime-local"
                value={values.when}
                onChange={(event) => set("when", event.target.value, "transaction_date")}
                {...fieldProps("transaction_date")}
              />
              {fieldError("transaction_date")}
            </label>
            <label className="field-label">
              Категория *
              <select
                value={values.categoryId}
                onChange={(event) => set("categoryId", event.target.value, "category_id")}
                {...fieldProps("category_id")}
              >
                <option value="">
                  {categoriesQuery.isLoading ? "Загрузка категорий…" : "Выберите категорию"}
                </option>
                {allowedCategories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </select>
              {fieldError("category_id")}
            </label>
            <label className="field-label">
              Счёт
              <select
                value={values.accountId}
                onChange={(event) => {
                  set("accountId", event.target.value, "account_id");
                  setErrors((current) => ({ ...current, currency: undefined }));
                }}
                {...fieldProps("account_id")}
              >
                <option value="">Не выбран</option>
                {selectableAccounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name} · {account.currency_code}
                    {account.is_archived ? " (архив)" : ""}
                  </option>
                ))}
              </select>
              {fieldError("account_id")}
            </label>
            <label className="field-label">
              Валюта
              <select
                disabled={Boolean(selectedAccount)}
                value={currency}
                onChange={(event) => set("currency", event.target.value, "currency")}
                {...fieldProps("currency")}
              >
                {currencyOptions.map((code) => (
                  <option key={code} value={code}>
                    {code}
                  </option>
                ))}
              </select>
              {selectedAccount && (
                <span className="transactions-currency-locked">Валюта счёта</span>
              )}
              {fieldError("currency")}
            </label>
            <label className="field-label">
              Банк
              <select
                value={values.bankId}
                onChange={(event) => set("bankId", event.target.value, "bank_id")}
                {...fieldProps("bank_id")}
              >
                <option value="">Не выбран</option>
                {banks.map((bank) => (
                  <option key={bank.id} value={bank.id}>
                    {bank.name}
                  </option>
                ))}
              </select>
              {fieldError("bank_id")}
            </label>
          </div>
          <label className="field-label">
            Описание
            <textarea
              maxLength={500}
              value={values.description}
              onChange={(event) => set("description", event.target.value, "description")}
              placeholder="Например, покупка в магазине"
              {...fieldProps("description")}
            />
            <span className="field-counter" aria-hidden="true">
              {values.description.length}/500
            </span>
            {fieldError("description")}
          </label>
          {referenceError && (
            <p className="form-error" role="alert">
              Не удалось загрузить справочники: {toUserMessage(referenceError)}
            </p>
          )}
          {formError && (
            <p className="form-error" role="alert">
              {formError}
            </p>
          )}
          <footer className="dialog-actions">
            <button type="button" className="button secondary" onClick={requestClose}>
              Отмена
            </button>
            <button type="submit" className="button primary" disabled={saving}>
              {saving ? "Сохраняем…" : transaction ? "Сохранить" : "Добавить операцию"}
            </button>
          </footer>
        </form>
      </section>
      {confirmDiscard && (
        <ConfirmDialog
          title="Отменить изменения?"
          description="Введённые данные не сохранятся."
          confirmLabel="Не сохранять"
          cancelLabel="Продолжить редактирование"
          danger
          onConfirm={onClose}
          onCancel={() => setConfirmDiscard(false)}
        />
      )}
    </div>
  );
}
