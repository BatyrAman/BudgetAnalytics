"use client";

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

import { EmptyState } from "@/components/common";
import { formatMoney, formatMonth, formatPercent } from "@/lib/format";
import type { CategoryAmount, CategoryBreakdown, Monthly } from "@/lib/types";

export const CHART_PALETTE = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
];

const tooltipStyle = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  color: "var(--text-primary)",
  padding: "8px 10px",
  fontSize: 13,
};

type MonthPoint = {
  label: string;
  monthTitle: string;
  income: string;
  netExpenses: string;
  // Numbers are used only for bar geometry; labels use the API strings.
  incomeValue: number;
  expensesValue: number;
};

export function MonthlyChart({ data }: { data: Monthly }) {
  const currency = data.currency_code;
  if (!data.months.some((month) => month.transaction_count > 0)) {
    return <EmptyState title="Нет данных для графика" description="За этот год нет операций" />;
  }
  const points: MonthPoint[] = data.months.map((month) => ({
    label: new Intl.DateTimeFormat("ru-KZ", { month: "short", timeZone: "UTC" })
      .format(new Date(`${month.month}-01T00:00:00Z`))
      .replace(".", ""),
    monthTitle: formatMonth(month.month),
    income: month.income,
    netExpenses: month.net_expenses,
    incomeValue: Number(month.income),
    expensesValue: Number(month.net_expenses),
  }));
  return (
    <div
      className="chart-wrap analytics-chart-wrap"
      role="img"
      aria-label="Доходы и расходы по месяцам; точные значения — в таблице"
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={points} margin={{ top: 10, right: 8, left: -12, bottom: 0 }}>
          <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(value) => `${Math.round(Number(value) / 1000)}к`}
          />
          <Tooltip
            content={({ active, payload }) => {
              const point: MonthPoint | undefined = payload?.[0]?.payload;
              if (!active || !point) return null;
              return (
                <div style={tooltipStyle}>
                  <b>{point.monthTitle}</b>
                  <div>Доходы: {formatMoney(point.income, currency, { hideZeroCents: true })}</div>
                  <div>
                    Расходы: {formatMoney(point.netExpenses, currency, { hideZeroCents: true })}
                  </div>
                </div>
              );
            }}
          />
          <Bar dataKey="incomeValue" name="Доходы" fill="var(--chart-1)" radius={[4, 4, 0, 0]} />
          <Bar dataKey="expensesValue" name="Расходы" fill="var(--chart-2)" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function MonthlyTable({ data }: { data: Monthly }) {
  const currency = data.currency_code;
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th scope="col">Месяц</th>
            <th scope="col">Доход</th>
            <th scope="col">Расходы</th>
            <th scope="col">Поток</th>
            <th scope="col">Норма сбережений</th>
          </tr>
        </thead>
        <tbody>
          {data.months.map((month) => (
            <tr key={month.month}>
              <th scope="row">{formatMonth(month.month)}</th>
              <td>{formatMoney(month.income, currency, { hideZeroCents: true })}</td>
              <td>{formatMoney(month.net_expenses, currency, { hideZeroCents: true })}</td>
              <td>{formatMoney(month.net_cash_flow, currency, { hideZeroCents: true })}</td>
              <td title={month.savings_rate === null ? "Нет доходов за месяц" : undefined}>
                {formatPercent(month.savings_rate, true)}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row">Итого за год</th>
            <td>{formatMoney(data.total.income, currency, { hideZeroCents: true })}</td>
            <td>{formatMoney(data.total.net_expenses, currency, { hideZeroCents: true })}</td>
            <td>{formatMoney(data.total.net_cash_flow, currency, { hideZeroCents: true })}</td>
            <td title={data.total.savings_rate === null ? "Нет доходов за год" : undefined}>
              {formatPercent(data.total.savings_rate, true)}
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

type Slice = CategoryAmount & { value: number };

export function CategoryDonut({ data }: { data: CategoryBreakdown }) {
  // Number() only for slice geometry; labels show the API strings.
  const slices: Slice[] = data.items.map((item) => ({ ...item, value: Number(item.amount) }));
  return (
    <div className="analytics-donut-wrap">
      <div
        className="analytics-donut"
        role="img"
        aria-label="Доли категорий; точные значения — в таблице"
      >
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={slices}
              dataKey="value"
              nameKey="name"
              innerRadius="68%"
              outerRadius="92%"
              paddingAngle={2}
            >
              {slices.map((item, index) => (
                <Cell key={item.category_id} fill={CHART_PALETTE[index % CHART_PALETTE.length]} />
              ))}
            </Pie>
            <Tooltip
              content={({ active, payload }) => {
                const slice: Slice | undefined = payload?.[0]?.payload;
                if (!active || !slice) return null;
                return (
                  <div style={tooltipStyle}>
                    <b>{slice.name}</b>
                    <div>
                      {formatMoney(slice.amount, data.currency_code, { hideZeroCents: true })} ·{" "}
                      {formatPercent(slice.share_percent)}
                    </div>
                  </div>
                );
              }}
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="analytics-donut-total">
          <span>Итого</span>
          <strong>{formatMoney(data.total, data.currency_code, { hideZeroCents: true })}</strong>
        </div>
      </div>
    </div>
  );
}
