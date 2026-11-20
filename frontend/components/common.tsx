import { ArrowDownRight, ArrowUpRight, CircleAlert, RefreshCw } from "lucide-react";
import { ApiError, toUserMessage } from "@/lib/api/errors";
import { formatMoney, formatPercent, formatPp } from "@/lib/format";

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
      {actions && <div className="page-heading-actions">{actions}</div>}
    </div>
  );
}
export function MetricCard({
  label,
  value,
  change,
  caption,
  loading = false,
  lowerIsBetter = false,
  changeUnit = "percent",
}: {
  label: string;
  value: string;
  change?: string | null;
  caption?: string;
  loading?: boolean;
  lowerIsBetter?: boolean;
  changeUnit?: "percent" | "pp";
}) {
  return (
    <section className="metric-card card-surface">
      {loading ? (
        <>
          <div className="skeleton-line short" />
          <div className="skeleton-line large" />
          <div className="skeleton-line medium" />
        </>
      ) : (
        <>
          <span className="metric-label">{label}</span>
          <strong className="metric-value tabular-nums">{value}</strong>
          <div className="metric-foot">
            {change && (
              <DeltaBadge value={change} lowerIsBetter={lowerIsBetter} unit={changeUnit} />
            )}
            <span>{caption}</span>
          </div>
        </>
      )}
    </section>
  );
}
export function MoneyText({
  amount,
  currency,
  sign,
}: {
  amount: string;
  currency: string;
  sign?: "+" | "−" | null;
}) {
  return <span className="money tabular-nums">{formatMoney(amount, currency, { sign })}</span>;
}
export function DeltaBadge({
  value,
  lowerIsBetter = false,
  unit = "percent",
}: {
  value: string;
  lowerIsBetter?: boolean;
  unit?: "percent" | "pp";
}) {
  const negative = value.startsWith("-");
  const favorable = lowerIsBetter ? negative : !negative;
  const formatted =
    unit === "pp"
      ? formatPp(value)
      : `${negative ? "−" : "+"}${formatPercent(value.replace(/^[+-]/, ""), true)}`;
  return (
    <span className={`delta ${favorable ? "positive-text" : "negative-text"}`}>
      {negative ? <ArrowDownRight size={14} /> : <ArrowUpRight size={14} />} {formatted}
    </span>
  );
}
export function StatusBadge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "positive" | "negative" | "warning" | "info" | "neutral";
}) {
  return <span className={`status-badge tone-${tone}`}>{children}</span>;
}
export function EmptyState({
  title = "Пока нет данных",
  description,
  action,
}: {
  title?: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon">
        <CircleAlert size={22} />
      </div>
      <b>{title}</b>
      <p>{description}</p>
      {action}
    </div>
  );
}
export function ErrorState({
  retry,
  error,
  title = "Не удалось загрузить данные",
}: {
  retry?: () => void;
  error?: unknown;
  title?: string;
}) {
  const requestId = error instanceof ApiError ? error.requestId : null;
  return (
    <div className="error-state" role="alert">
      <CircleAlert size={22} aria-hidden="true" />
      <b>{title}</b>
      <span>{error ? toUserMessage(error) : "Попробуйте повторить запрос."}</span>
      {retry && (
        <button className="button secondary" type="button" onClick={retry}>
          <RefreshCw size={15} aria-hidden="true" /> Повторить
        </button>
      )}
      {requestId && <small>Код запроса: {requestId}</small>}
    </div>
  );
}
export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton-line ${className}`} aria-label="Загрузка" />;
}
export function SkeletonCard() {
  return (
    <div className="card-surface skeleton-card">
      <Skeleton className="short" />
      <Skeleton className="large" />
      <Skeleton className="medium" />
    </div>
  );
}
export function ChartCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="chart-card card-surface">
      <header>
        <div>
          <h3>{title}</h3>
          {subtitle && <p>{subtitle}</p>}
        </div>
      </header>
      {children}
    </section>
  );
}
export function Legend({
  items,
}: {
  items: {
    name: string;
    color: string;
    amount: string;
    currency: string;
    share: string;
  }[];
}) {
  return (
    <div className="legend">
      {items.map((i) => (
        <div className="legend-row" key={i.name}>
          <span className="legend-name">
            <i style={{ backgroundColor: i.color }} />
            {i.name}
          </span>
          <span className="legend-amount">
            {formatMoney(i.amount, i.currency, { hideZeroCents: true })}
          </span>
          <span className="legend-share">{formatPercent(i.share)}</span>
        </div>
      ))}
    </div>
  );
}
export function BackendBadge() {
  return <span className="backend-badge">Требует backend</span>;
}
