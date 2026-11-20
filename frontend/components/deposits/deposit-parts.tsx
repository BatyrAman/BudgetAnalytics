import { formatMoney } from "@/lib/format";
import type { Maturity } from "@/lib/types";

import { formatRateExact, translateAssumptions } from "./deposit-utils";

export function DetailLine({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="deposit-detail-line">
      <span>{label}</span>
      <strong className="tabular-nums">{children}</strong>
    </div>
  );
}

/** Backend maturity estimate; every number comes from the API as a string. */
export function MaturityFacts({ maturity, currency }: { maturity: Maturity; currency: string }) {
  return (
    <dl className="deposit-maturity-facts">
      <div>
        <dt>Доход</dt>
        <dd>{formatMoney(maturity.interest, currency)}</dd>
      </div>
      <div>
        <dt>Сумма к концу срока</dt>
        <dd>{formatMoney(maturity.maturity_amount, currency)}</dd>
      </div>
      <div>
        <dt>Эффективная годовая ставка (расчёт)</dt>
        <dd>
          {maturity.effective_annual_rate === null ? (
            <span title="Без капитализации эффективная ставка не рассчитывается">—</span>
          ) : (
            formatRateExact(maturity.effective_annual_rate)
          )}
        </dd>
      </div>
      <div>
        <dt>Дней в сроке</dt>
        <dd>{maturity.term_days}</dd>
      </div>
      <div>
        <dt>Периодов капитализации</dt>
        <dd>{maturity.capitalization_periods}</dd>
      </div>
      <div>
        <dt>Дней без капитализации («хвост»)</dt>
        <dd>{maturity.stub_days}</dd>
      </div>
    </dl>
  );
}

export function Assumptions({ items }: { items: string[] }) {
  const { known, unknown } = translateAssumptions(items);
  if (known.length === 0 && unknown.length === 0) return null;
  return (
    <section className="deposit-assumptions">
      <h3>Допущения расчёта</h3>
      {known.length > 0 && (
        <ul>
          {known.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
      {unknown.length > 0 && (
        <>
          <p>
            <small>Допущения backend</small>
          </p>
          <ul lang="en">
            {unknown.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

export function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <small id={id} className="deposit-field-error" role="alert">
      {message}
    </small>
  );
}
