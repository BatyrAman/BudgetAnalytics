"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { useTimezone } from "@/components/analytics/analytics-filters";
import { todayInTimezone } from "@/components/analytics/period";
import { AppShell } from "@/components/app-shell";
import { EmptyState, PageHeader } from "@/components/common";
import { calculateDeposit, type DepositCalculationInput } from "@/lib/api/client";
import { ApiError, toUserMessage } from "@/lib/api/errors";
import { useDefaultCurrency } from "@/lib/api/hooks";
import { formatDate, formatMoney, formatPercent } from "@/lib/format";
import type { Capitalization, DepositCalculation } from "@/lib/types";

import { DepositFormDialog } from "./deposit-form";
import { Assumptions, DetailLine, FieldError, MaturityFacts } from "./deposit-parts";
import {
  CAPITALIZATION_LABELS,
  MATURITY_TOO_LATE,
  MAX_DEPOSIT_DATE,
  SUPPORTED_CURRENCIES,
  addMonthsIso,
  dateBoundError,
  dateRangeError,
  depositFieldErrors,
  nominalRateError,
  normalizeDecimal,
  principalError,
  termMonthsError,
} from "./deposit-utils";

type Field =
  | "principal"
  | "currency"
  | "interest_rate"
  | "capitalization"
  | "start_date"
  | "end_date"
  | "term_months";
type Errors = Partial<Record<Field, string>>;
const FIELDS = new Set<string>([
  "principal",
  "currency",
  "interest_rate",
  "capitalization",
  "start_date",
  "end_date",
  "term_months",
]);

function CalculationResult({ result, onSave }: { result: DepositCalculation; onSave: () => void }) {
  const currency = result.currency_code;
  return (
    <>
      <div className="deposit-result-hero">
        <span>Доход к концу срока</span>
        <strong className="tabular-nums">{formatMoney(result.maturity.interest, currency)}</strong>
        <small>Это оценка, а не предложение банка</small>
      </div>
      <DetailLine label="Сумма к концу срока">
        {formatMoney(result.maturity.maturity_amount, currency)}
      </DetailLine>
      <DetailLine label="Дата окончания">{formatDate(result.maturity_date)}</DetailLine>
      <DetailLine label="Номинальная ставка">
        {formatPercent(result.interest_rate, true)}
      </DetailLine>
      <MaturityFacts maturity={result.maturity} currency={currency} />
      <Assumptions items={result.maturity.assumptions} />
      <button type="button" className="button primary save-deposit-button" onClick={onSave}>
        Сохранить как депозит
      </button>
    </>
  );
}

export function DepositCalculator() {
  const router = useRouter();
  const defaultCurrency = useDefaultCurrency();
  const today = todayInTimezone(useTimezone());
  const resultRef = useRef<HTMLElement>(null);
  const [values, setValues] = useState({
    principal: "",
    currency: "",
    interest_rate: "",
    capitalization: "monthly" as Capitalization,
    start_date: "",
    end_date: "",
    term_months: "",
  });
  const [termMode, setTermMode] = useState<"date" | "months">("months");
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<DepositCalculation | null>(null);
  const [saving, setSaving] = useState(false);

  const currency = values.currency || defaultCurrency;
  const startDate = values.start_date || today;

  const set = (field: Field) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setValues((current) => ({ ...current, [field]: event.target.value }));

  function validate(): Errors {
    const next: Errors = {};
    const principal = principalError(values.principal);
    if (principal) next.principal = principal;
    const rate = nominalRateError(values.interest_rate);
    if (rate) next.interest_rate = rate;
    if (termMode === "months") {
      if (!startDate) next.start_date = "Укажите дату начала.";
      else {
        const bound = dateBoundError(startDate);
        if (bound) next.start_date = bound;
      }
      const term = termMonthsError(values.term_months);
      if (term) next.term_months = term;
      // The end computed from the term must not pass the last allowed date.
      else if (!next.start_date) {
        const end = addMonthsIso(startDate, Number(values.term_months.trim()));
        if (end > MAX_DEPOSIT_DATE) next.term_months = MATURITY_TOO_LATE;
      }
    } else {
      const dates = dateRangeError(startDate, values.end_date);
      if (dates.start) next.start_date = dates.start;
      if (dates.end) next.end_date = dates.end;
    }
    return next;
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const next = validate();
    setErrors(next);
    setFormError("");
    if (Object.keys(next).length > 0) return;
    // Exactly one of end_date / term_months is sent.
    const input: DepositCalculationInput = {
      principal: normalizeDecimal(values.principal),
      currency,
      interest_rate: normalizeDecimal(values.interest_rate),
      capitalization: values.capitalization,
      start_date: startDate,
      ...(termMode === "date"
        ? { end_date: values.end_date }
        : { term_months: Number(values.term_months.trim()) }),
    };
    setBusy(true);
    try {
      const calculated = await calculateDeposit(input);
      setResult(calculated);
      if (typeof window !== "undefined" && window.innerWidth < 768) {
        window.setTimeout(
          () => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
          40,
        );
      }
    } catch (reason) {
      setResult(null);
      const apiErrors: Errors = {};
      if (reason instanceof ApiError) {
        if (reason.code === "unknown_currency") apiErrors.currency = toUserMessage(reason);
        if (reason.code === "invalid_date_range") {
          apiErrors[termMode === "date" ? "end_date" : "term_months"] = toUserMessage(reason);
        }
        const termField = termMode === "date" ? "end_date" : "term_months";
        for (const item of depositFieldErrors(reason.fieldErrors, termField)) {
          if (FIELDS.has(item.field)) apiErrors[item.field as Field] = item.message;
        }
      }
      setErrors(apiErrors);
      if (Object.keys(apiErrors).length === 0) setFormError(toUserMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  const describe = (field: Field) => (errors[field] ? `calc-${field}-error` : undefined);
  const invalid = (field: Field) => (errors[field] ? true : undefined);
  const switchMode = (mode: "date" | "months") => {
    setTermMode(mode);
    setErrors((current) => ({ ...current, end_date: undefined, term_months: undefined }));
  };

  return (
    <div className="entity-page deposits-page">
      <Link href="/deposits" className="back-link">
        ← Все депозиты
      </Link>
      <PageHeader
        title="Калькулятор депозита"
        description="Оцените доходность по заданным условиям. Расчёт не сохраняется"
      />
      <div className="deposit-calculator-layout">
        <form className="deposit-calculator-form card-surface" onSubmit={submit} noValidate>
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
            <FieldError id="calc-principal-error" message={errors.principal} />
          </label>
          <div className="form-two">
            <label className="field-label">
              Валюта
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
              <FieldError id="calc-currency-error" message={errors.currency} />
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
              <FieldError id="calc-interest_rate-error" message={errors.interest_rate} />
            </label>
          </div>
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
          <label className="field-label">
            Дата начала *
            <input
              name="start_date"
              type="date"
              value={startDate}
              onChange={set("start_date")}
              aria-invalid={invalid("start_date")}
              aria-describedby={describe("start_date")}
            />
            <FieldError id="calc-start_date-error" message={errors.start_date} />
          </label>
          <div
            className="segmented-control term-switch"
            role="group"
            aria-label="Способ задания срока"
          >
            <button
              type="button"
              className={termMode === "date" ? "selected" : ""}
              aria-pressed={termMode === "date"}
              onClick={() => switchMode("date")}
            >
              Дата окончания
            </button>
            <button
              type="button"
              className={termMode === "months" ? "selected" : ""}
              aria-pressed={termMode === "months"}
              onClick={() => switchMode("months")}
            >
              Срок в месяцах
            </button>
          </div>
          {termMode === "date" ? (
            <label className="field-label">
              Дата окончания *
              <input
                name="end_date"
                type="date"
                value={values.end_date}
                min={startDate || undefined}
                onChange={set("end_date")}
                aria-invalid={invalid("end_date")}
                aria-describedby={describe("end_date")}
              />
              <FieldError id="calc-end_date-error" message={errors.end_date} />
            </label>
          ) : (
            <label className="field-label">
              Срок в месяцах *
              <input
                name="term_months"
                inputMode="numeric"
                autoComplete="off"
                value={values.term_months}
                onChange={set("term_months")}
                aria-invalid={invalid("term_months")}
                aria-describedby={[describe("term_months"), "calc-term_months-hint"]
                  .filter(Boolean)
                  .join(" ")}
              />
              <small id="calc-term_months-hint" aria-hidden="true">
                От 1 до 600
              </small>
              <FieldError id="calc-term_months-error" message={errors.term_months} />
            </label>
          )}
          {formError && (
            <p className="form-error" role="alert">
              {formError}
            </p>
          )}
          <button type="submit" className="button primary calculate-button" disabled={busy}>
            {busy ? "Рассчитываем…" : "Рассчитать"}
          </button>
        </form>
        <section
          className="deposit-calculator-result card-surface"
          ref={resultRef}
          aria-live="polite"
          aria-busy={busy}
        >
          <h2>Результат расчёта</h2>
          {result ? (
            <CalculationResult result={result} onSave={() => setSaving(true)} />
          ) : (
            <EmptyState
              title="Заполните условия вклада"
              description="Результат появится после нажатия «Рассчитать»"
            />
          )}
        </section>
      </div>
      {saving && result && (
        <DepositFormDialog
          prefill={{
            principal: result.principal,
            currency: result.currency_code,
            interest_rate: result.interest_rate,
            capitalization: result.capitalization,
            start_date: result.start_date,
            end_date: result.maturity_date,
          }}
          onClose={() => setSaving(false)}
          onSaved={(saved) => router.push(`/deposits/${saved.id}`)}
        />
      )}
    </div>
  );
}

export function DepositCalculatorScreen() {
  return (
    <AppShell>
      <DepositCalculator />
    </AppShell>
  );
}
