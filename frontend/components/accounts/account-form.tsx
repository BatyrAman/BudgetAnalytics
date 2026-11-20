"use client";

import { useState } from "react";
import {
  createAccount,
  currentTimezone,
  updateAccount,
  type AccountInput,
  type AccountPatch,
} from "@/lib/api/client";
import { ApiError, toUserMessage } from "@/lib/api/errors";
import { useBanks, useDefaultCurrency } from "@/lib/api/hooks";
import { parseLocalDate } from "@/lib/timezone";
import type { Account } from "@/lib/types";
import {
  STATIC_CURRENCIES,
  accountTypeLabels,
  canonicalAmount,
  dateInZone,
  isAccountType,
  orderCurrencies,
  parseSignedAmount,
  startOfDayIso,
} from "./account-meta";

type FieldName =
  | "name"
  | "account_type"
  | "currency"
  | "bank_id"
  | "last4"
  | "opening_balance"
  | "opening_balance_at";
type Errors = Partial<Record<FieldName, string>>;

const FIELDS: FieldName[] = [
  "name",
  "account_type",
  "currency",
  "bank_id",
  "last4",
  "opening_balance",
  "opening_balance_at",
];
const isField = (value: string): value is FieldName => (FIELDS as string[]).includes(value);

/** Business error codes that belong to a specific field. */
const CODE_FIELDS: Record<string, FieldName> = {
  account_name_taken: "name",
  bank_not_found: "bank_id",
  unknown_currency: "currency",
};

function mapApiError(error: unknown): { fields: Errors; form: string } {
  if (!(error instanceof ApiError)) return { fields: {}, form: toUserMessage(error) };
  const codeField = CODE_FIELDS[error.code];
  if (codeField) return { fields: { [codeField]: toUserMessage(error) }, form: "" };
  const fields: Errors = {};
  for (const issue of error.fieldErrors) {
    const name = issue.field.split(".")[0];
    if (isField(name) && !fields[name]) fields[name] = issue.message;
  }
  return Object.keys(fields).length
    ? { fields, form: "" }
    : { fields: {}, form: toUserMessage(error) };
}

function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <small id={id} className="field-error text-negative" role="alert">
      {message}
    </small>
  );
}

/** Create (AC-1) or edit (AC-2) an account. Currency is fixed after creation. */
export function AccountFormDialog({
  account,
  onClose,
  onSaved,
}: {
  account?: Account;
  onClose: () => void;
  onSaved: (account: Account) => Promise<void> | void;
}) {
  const editing = Boolean(account);
  const timeZone = currentTimezone();
  const defaultCurrency = useDefaultCurrency();
  const { data: banks = [] } = useBanks();
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);
  const initialDate = account ? dateInZone(timeZone, new Date(account.opening_balance_at)) : "";
  const currencies = orderCurrencies([...STATIC_CURRENCIES, defaultCurrency], defaultCurrency);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    const form = new FormData(event.currentTarget);
    const value = (name: FieldName) => String(form.get(name) ?? "").trim();
    const next: Errors = {};

    const name = value("name");
    if (name.length < 1 || name.length > 100)
      next.name = "Название должно содержать от 1 до 100 символов.";
    const type = value("account_type");
    if (!isAccountType(type)) next.account_type = "Выберите тип счёта.";
    const last4 = value("last4");
    if (last4 && !/^[0-9]{4}$/.test(last4)) next.last4 = "Укажите ровно 4 цифры.";
    const balance = parseSignedAmount(value("opening_balance") || "0");
    if (balance === null) next.opening_balance = "Введите сумму, не больше 2 знаков после запятой.";
    const date = value("opening_balance_at");
    if (!parseLocalDate(date)) next.opening_balance_at = "Укажите дату.";

    setErrors(next);
    if (Object.keys(next).length || balance === null || !isAccountType(type)) return;

    const bankRaw = value("bank_id");
    const common = {
      name,
      account_type: type,
      bank_id: bankRaw ? Number(bankRaw) : null,
      last4: last4 || null,
    };
    setBusy(true);
    try {
      let saved: Account;
      if (account) {
        const patch: AccountPatch = { ...common };
        if (canonicalAmount(balance) !== canonicalAmount(account.opening_balance))
          patch.opening_balance = balance;
        if (date !== initialDate) patch.opening_balance_at = startOfDayIso(date, timeZone);
        saved = await updateAccount(account.id, patch);
      } else {
        const input: AccountInput = {
          ...common,
          currency: value("currency"),
          opening_balance: balance,
          opening_balance_at: startOfDayIso(date, timeZone),
        };
        saved = await createAccount(input);
      }
      await onSaved(saved);
    } catch (error) {
      const mapped = mapApiError(error);
      setErrors(mapped.fields);
      setFormError(mapped.form);
    } finally {
      setBusy(false);
    }
  }

  const described = (field: FieldName, hint?: string) =>
    [errors[field] ? `account-${field}-error` : "", hint ?? ""].filter(Boolean).join(" ") ||
    undefined;

  return (
    <div
      className="overlay-backdrop"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
      onKeyDown={(event) => event.key === "Escape" && onClose()}
    >
      <section
        className="demo-dialog account-form-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="account-form-title"
      >
        <button type="button" className="dialog-close" onClick={onClose} aria-label="Закрыть">
          ×
        </button>
        <h2 id="account-form-title">{editing ? "Изменить счёт" : "Новый счёт"}</h2>
        <form className="entity-form" onSubmit={submit} noValidate>
          <label className="field-label">
            Название *
            <input
              name="name"
              required
              maxLength={100}
              autoFocus
              defaultValue={account?.name ?? ""}
              aria-invalid={Boolean(errors.name)}
              aria-describedby={described("name")}
            />
            <FieldError id="account-name-error" message={errors.name} />
          </label>
          <div className="form-two">
            <label className="field-label">
              Тип *
              <select
                name="account_type"
                defaultValue={account?.account_type ?? "card"}
                aria-invalid={Boolean(errors.account_type)}
                aria-describedby={described("account_type")}
              >
                {Object.entries(accountTypeLabels).map(([type, label]) => (
                  <option key={type} value={type}>
                    {label}
                  </option>
                ))}
              </select>
              <FieldError id="account-account_type-error" message={errors.account_type} />
            </label>
            <label className="field-label">
              Валюта
              {account ? (
                <input value={account.currency_code} disabled readOnly />
              ) : (
                <select
                  name="currency"
                  defaultValue={defaultCurrency}
                  aria-invalid={Boolean(errors.currency)}
                  aria-describedby={described("currency", "account-currency-hint")}
                >
                  {currencies.map((code) => (
                    <option key={code} value={code}>
                      {code}
                    </option>
                  ))}
                </select>
              )}
              <small id="account-currency-hint" aria-hidden="true">
                Валюту нельзя изменить после создания
              </small>
              <FieldError id="account-currency-error" message={errors.currency} />
            </label>
          </div>
          <label className="field-label">
            Банк
            <select
              name="bank_id"
              defaultValue={account?.bank_id ?? ""}
              aria-invalid={Boolean(errors.bank_id)}
              aria-describedby={described("bank_id")}
            >
              <option value="">Не выбран</option>
              {banks.map((bank) => (
                <option key={bank.id} value={bank.id}>
                  {bank.name}
                </option>
              ))}
            </select>
            <FieldError id="account-bank_id-error" message={errors.bank_id} />
          </label>
          <label className="field-label">
            Последние 4 цифры
            <input
              name="last4"
              inputMode="numeric"
              maxLength={4}
              pattern="[0-9]{4}"
              placeholder="0000"
              autoComplete="off"
              defaultValue={account?.last4 ?? ""}
              aria-invalid={Boolean(errors.last4)}
              aria-describedby={described("last4", "account-last4-hint")}
            />
            <small id="account-last4-hint" aria-hidden="true">
              Никогда не вводите полный номер карты, CVV или PIN
            </small>
            <FieldError id="account-last4-error" message={errors.last4} />
          </label>
          <label className="field-label">
            Начальный остаток
            <input
              name="opening_balance"
              inputMode="decimal"
              defaultValue={account?.opening_balance ?? "0"}
              aria-invalid={Boolean(errors.opening_balance)}
              aria-describedby={described("opening_balance", "account-balance-hint")}
            />
            <small id="account-balance-hint" aria-hidden="true">
              Для кредитной карты укажите долг со знаком минус
            </small>
            <FieldError id="account-opening_balance-error" message={errors.opening_balance} />
          </label>
          <label className="field-label">
            Дата начального остатка
            <input
              name="opening_balance_at"
              type="date"
              defaultValue={initialDate || dateInZone(timeZone)}
              required
              aria-invalid={Boolean(errors.opening_balance_at)}
              aria-describedby={described("opening_balance_at", "account-date-hint")}
            />
            <small id="account-date-hint" aria-hidden="true">
              Операции до этой даты не учитываются в балансе
            </small>
            <FieldError id="account-opening_balance_at-error" message={errors.opening_balance_at} />
          </label>
          {formError && (
            <p className="form-error" role="alert">
              {formError}
            </p>
          )}
          <div className="dialog-actions">
            <button type="button" className="button secondary" onClick={onClose}>
              Отмена
            </button>
            <button type="submit" className="button primary" disabled={busy}>
              {busy ? "Сохранение…" : editing ? "Сохранить" : "Создать счёт"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
