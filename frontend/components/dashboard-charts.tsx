"use client";
import { useSyncExternalStore } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { CategoryBreakdown, Monthly, MonthSummary } from "@/lib/types";
import { formatMoney, formatPercent } from "@/lib/format";

const colors = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
];
const tooltipStyle = {
  background: "var(--surface)",
  borderColor: "var(--border)",
  borderRadius: 8,
  color: "var(--text-primary)",
};
const MOBILE_QUERY = "(max-width: 700px)";

function subscribeMobile(onChange: () => void) {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return () => {};
  const query = window.matchMedia(MOBILE_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}
function isMobileViewport() {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia(MOBILE_QUERY).matches
  );
}
function useIsMobile() {
  return useSyncExternalStore(subscribeMobile, isMobileViewport, () => false);
}

/**
 * Months shown on the cash-flow chart: all months of the year returned by the API,
 * or — on mobile — the last six months up to and including `currentMonth` (YYYY-MM).
 */
export function cashflowMonths(
  months: MonthSummary[],
  currentMonth: string,
  mobile: boolean,
): MonthSummary[] {
  if (!mobile) return months;
  const upToCurrent = months.filter((month) => month.month <= currentMonth);
  return upToCurrent.slice(-6);
}

const monthLabel = (month: string) =>
  new Intl.DateTimeFormat("ru-KZ", { month: "short", timeZone: "UTC" })
    .format(new Date(`${month}-01T00:00:00Z`))
    .replace(".", "");

export function CashflowChart({ data, currentMonth }: { data: Monthly; currentMonth: string }) {
  const mobile = useIsMobile();
  const currency = data.currency_code;
  // Number() is used for chart geometry only; labels are formatted from the API strings.
  const points = cashflowMonths(data.months, currentMonth, mobile).map((m) => ({
    name: monthLabel(m.month),
    income: Number(m.income),
    expenses: Number(m.net_expenses),
    incomeLabel: m.income,
    expensesLabel: m.net_expenses,
  }));
  return (
    <div className="chart-wrap cashflow-wrap">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={points} margin={{ top: 8, right: 0, bottom: 0, left: -12 }}>
          <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
          <XAxis
            dataKey="name"
            tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v: number) => `${Math.round(v / 1000)}к`}
          />
          <Tooltip
            formatter={(_value, name, item) => {
              const payload = item.payload as (typeof points)[number];
              const raw = name === "Доход" ? payload.incomeLabel : payload.expensesLabel;
              return formatMoney(raw, currency, { hideZeroCents: true });
            }}
            contentStyle={tooltipStyle}
          />
          <Bar dataKey="income" name="Доход" fill="var(--chart-1)" radius={[4, 4, 0, 0]} />
          <Bar dataKey="expenses" name="Расход" fill="var(--chart-2)" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ExpenseDonut({ data }: { data: CategoryBreakdown }) {
  const currency = data.currency_code;
  const items = data.items.map((item, i) => ({
    ...item,
    // Chart geometry only.
    value: Number(item.amount),
    fill: colors[Math.min(i, colors.length - 1)],
  }));
  return (
    <div className="donut-layout">
      <div className="donut">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={items}
              dataKey="value"
              nameKey="name"
              innerRadius="65%"
              outerRadius="92%"
              paddingAngle={2}
              stroke="none"
            >
              {items.map((item) => (
                <Cell key={item.category_id} fill={item.fill} />
              ))}
            </Pie>
            <Tooltip
              formatter={(_value, _name, item) =>
                formatMoney((item.payload as (typeof items)[number]).amount, currency, {
                  hideZeroCents: true,
                })
              }
              contentStyle={tooltipStyle}
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="donut-center">
          <b>{formatMoney(data.total, currency, { hideZeroCents: true })}</b>
          <span>Расходы</span>
        </div>
      </div>
      <div className="donut-legend">
        {items.map((i) => (
          <div key={i.category_id} className="donut-row">
            <span className="donut-label">
              <i style={{ background: i.fill }} aria-hidden="true" />
              {i.name}
            </span>
            <span className="donut-values">
              {formatMoney(i.amount, currency, { hideZeroCents: true })}
              <small>{formatPercent(i.share_percent)}</small>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
