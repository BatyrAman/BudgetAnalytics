"use client";

import { useEffect, useRef, useState } from "react";
import { useSWRConfig } from "swr";

import { createDeposit, updateDeposit, type DepositInput } from "@/lib/api/client";
import { ApiError, toUserMessage } from "@/lib/api/errors";
import { useBanks, useDefaultCurrency } from "@/lib/api/hooks";
import type { Capitalization, Deposit } from "@/lib/types";

import { useTimezone } from "@/components/analytics/analytics-filters";
import { todayInTimezone } from "@/components/analytics/period";

import { FieldError } from "./deposit-parts";
import {
  CAPITALIZATION_LABELS,
  SUPPORTED_CURRENCIES,
  dateRangeError,
  effectiveRateError,
  nominalRateError,
  normalizeDecimal,
  principalError,
} from "./deposit-utils";

export type DepositPrefill = {
  principal?: string;
  currency?: string;
  interest_rate?: string;
  capitalization?: Capitalization;
  start_date?: string;
  end_date?: string;
};

type Field =
  | "bank_id"
  | "principal"
  | "currency"
  | "interest_rate"
  | "effective_rate"
  | "capitalization"
  | "start_date"
  | "end_date";
type Errors = Partial<Record<Field, string>>;

const FIELDS = new Set<string>([
  "bank_id",
  "principal",
  "currency",
  "interest_rate",
  "effective_rate",
  "capitalization",
  "start_date",
  "end_date",
]);

/** Revalidates every cached deposit list/detail and the overview (deposit totals). */
export function useRevalidateDeposits() {
  const { mutate } = useSWRConfig();
  return () =>
    mutate(
      (key) => Array.isArray(key) && ["deposits", "deposit", "overview"].includes(String(key[0])),
    );
}

export function DepositFormDialog({
  deposit,
  prefill,
  onClose,
  onSaved,
}: {
  /** Existing deposit to edit; omitted for a new one. */
  deposit?: Deposit;
  prefill?: DepositPrefill;
  onClose: () => void;
  onSaved?: (saved: Deposit) => void;
}) {
  const banks = useBanks();
  const defaultCurrency = useDefaultCurrency();
  const today = todayInTimezone(useTimezone());
  const revalidate = useRevalidateDeposits();
  const dialogRef = useRef<HTMLElement>(null);

  const [values, setValues] = useState({
    bank_id: deposit ? String(deposit.bank_id) : "",
    principal: deposit?.principal ?? prefill?.principal ?? "",
    currency: deposit?.currency_code ?? prefill?.currency ?? "",
    interest_rate: deposit?.interest_rate ?? prefill?.interest_rate ?? "",
    effective_rate: deposit?.effective_rate ?? "",
    capitalization: deposit?.capitalization ?? prefill?.capitalization ?? "monthly",
    start_date: deposit?.start_date ?? prefill?.start_date ?? today,
    end_date: deposit?.end_date ?? prefill?.end_date ?? "",
  });
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);
  const currency = values.currency || defaultCurrency;

  useEffect(() => {
    dialogRef.current?.querySelector<HTMLElement>("select:not([disabled]), input")?.focus();
  }, []);

  const set = (field: Field) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setValues((current) => ({ ...current, [field]: event.target.value }));

  function validate(): Errors {
    const next: Errors = {};
    if (!values.bank_id) next.bank_id = "Выберите банк.";
    const principal = principalError(values.principal);
    if (principal) next.principal = principal;
    const rate = nominalRateError(values.interest_rate);
    if (rate) next.interest_rate = rate;
    const effective = effectiveRateError(values.effective_rate);
    if (effective) next.effective_rate = effective;
    const dates = dateRangeError(values.start_date, values.end_date);
    if (dates.start) next.start_date = dates.start;
    if (dates.end) next.end_date = dates.end;
    return next;
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const next = validate();
    setErrors(next);
    setFormError("");
    if (Object.keys(next).length > 0) return;
    const effective = normalizeDecimal(values.effective_rate);
    const payload: DepositInput = {
      bank_id: Number(values.bank_id),
      principal: normalizeDecimal(values.principal),
      interest_rate: normalizeDecimal(values.interest_rate),
      capitalization: values.capitalization,
      start_date: values.start_date,
      end_date: values.end_date,
    };
    setBusy(true);
    try {
      let saved: Deposit;
      if (deposit) {
        // Currency of an existing deposit cannot be changed (PATCH has no `currency`).
        saved = await updateDeposit(deposit.id, { ...payload, effective_rate: effective || null });
      } else {
        saved = await createDeposit({
          ...payload,
          currency,
          ...(effective ? { effective_rate: effective } : {}),
        });
      }
      await revalidate();
      onSaved?.(saved);
      onClose();
    } catch (reason) {
      const apiErrors: Errors = {};
      if (reason instanceof ApiError) {
        if (reason.code === "bank_not_found") apiErrors.bank_id = toUserMessage(reason);
        if (reason.code === "invalid_date_range") apiErrors.end_date = toUserMessage(reason);
        if (reason.code === "unknown_currency") apiErrors.currency = toUserMessage(reason);
        for (const item of reason.fieldErrors) {
          if (FIELDS.has(item.field)) apiErrors[item.field as Field] = item.message;
        }
      }
      setErrors(apiErrors);
      if (Object.keys(apiErrors).length === 0 || !(reason instanceof ApiError)) {
        setFormError(toUserMessage(reason));
      } else if (reason.fieldErrors.some((item) => !FIELDS.has(item.field))) {
        setFormError("Проверьте правильность заполнения полей.");
      }
    } finally {
      setBusy(false);
    }
  }

  const describe = (field: Field) => (errors[field] ? `deposit-${field}-error` : undefined);
  const invalid = (field: Field) => (errors[field] ? true : undefined);

  return (
    <div
      className="overlay-backdrop"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <section
        ref={dialogRef}
        className="demo-dialog deposit-form-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="deposit-form-title"
        onKeyDown={(event) => event.key === "Escape" && onClose()}
      >
        <button className="dialog-close" type="button" onClick={onClose} aria-label="Закрыть">
          ×
        </button>
        <h2 id="deposit-form-title">{deposit ? "Изменить депозит" : "Добавить депозит"}</h2>
        <form className="entity-form" onSubmit={submit} noValidate>
          <label className="field-label">
            Банк *
            <select
              name="bank_id"
              value={values.bank_id}
              onChange={set("bank_id")}
              aria-invalid={invalid("bank_id")}
              aria-describedby={describe("bank_id")}
              disabled={!banks.data}
            >
              <option value="">{banks.data ? "Выберите банк" : "Загрузка банков…"}</option>
              {banks.data?.map((bank) => (
                <option key={bank.id} value={bank.id}>
                  {bank.name}
                </option>
              ))}
            </select>
            {banks.error && (
              <small className="deposit-field-error">
                {toUserMessage(banks.error)}{" "}
                <button
                  type="button"
                  className="button secondary"
                  onClick={() => void banks.mutate()}
                >
                  Повторить
                </button>
              </small>
            )}
            <FieldError id="deposit-bank_id-error" message={errors.bank_id} />
          </label>
          <label className="field-label">
            Сумма *
            <input
              name="principal"
              inputMode="decimal"
              autoComplete="off"
              value={values.principal}
              onChange={set("principal")}
              aria-invalid={invalid("principal")}
              aria-describedby={describe("principal")}
            />
            <FieldError id="deposit-principal-error" message={errors.principal} />
          </label>
          <div className="form-two">
            <label className="field-label">
              Валюта
              {deposit ? (
                <input name="currency" value={deposit.currency_code} readOnly />
              ) : (
                <select
                  name="currency"
                  value={currency}
                  onChange={set("currency")}
                  aria-invalid={invalid("currency")}
                  aria-describedby={describe("currency")}
                >
                  {[...new Set([currency, ...SUPPORTED_CURRENCIES])].map((code) => (
                    <option key={code} value={code}>
                      {code}
                    </option>
                  ))}
                </select>
              )}
              {deposit && <small>Валюту вклада изменить нельзя</small>}
              <FieldError id="deposit-currency-error" message={errors.currency} />
            </label>
            <label className="field-label">
              Номинальная ставка, % *
              <input
                name="interest_rate"
                inputMode="decimal"
                autoComplete="off"
                value={values.interest_rate}
                onChange={set("interest_rate")}
                aria-invalid={invalid("interest_rate")}
                aria-describedby={describe("interest_rate")}
              />
              <FieldError id="deposit-interest_rate-error" message={errors.interest_rate} />
            </label>
          </div>
          <label className="field-label">
            ГЭСВ (по данным банка), % — необязательно
            <input
              name="effective_rate"
              inputMode="decimal"
              autoComplete="off"
              value={values.effective_rate}
              onChange={set("effective_rate")}
              aria-invalid={invalid("effective_rate")}
              aria-describedby={[describe("effective_rate"), "deposit-effective_rate-hint"]
                .filter(Boolean)
                .join(" ")}
            />
            <small id="deposit-effective_rate-hint" aria-hidden="true">
              Как указано в договоре; в расчётах не используется
            </small>
            <FieldError id="deposit-effective_rate-error" message={errors.effective_rate} />
          </label>
          <label className="field-label">
            Капитализация
            <select
              name="capitalization"
              value={values.capitalization}
              onChange={set("capitalization")}
            >
              {Object.entries(CAPITALIZATION_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <div className="form-two">
            <label className="field-label">
              Дата начала *
              <input
                name="start_date"
                type="date"
                value={values.start_date}
                onChange={set("start_date")}
                aria-invalid={invalid("start_date")}
                aria-describedby={describe("start_date")}
              />
              <FieldError id="deposit-start_date-error" message={errors.start_date} />
            </label>
            <label className="field-label">
              Дата окончания *
              <input
                name="end_date"
                type="date"
                value={values.end_date}
                min={values.start_date || undefined}
                onChange={set("end_date")}
                aria-invalid={invalid("end_date")}
                aria-describedby={describe("end_date")}
              />
              <FieldError id="deposit-end_date-error" message={errors.end_date} />
            </label>
          </div>
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
              {busy ? "Сохранение…" : "Сохранить депозит"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
