"use client";

import { useEffect, useRef, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { toast } from "sonner";
import {
  ChartCard,
  EmptyState,
  ErrorState,
  MetricCard,
  SkeletonCard,
  StatusBadge,
  BackendBadge,
} from "@/components/common";
import { StateSections } from "@/components/design-system/state-sections";
import { formatMoney, formatPercent } from "@/lib/format";

const tokenRows = [
  ["Фон", "background", "#F4F6F8", "#0D1117"],
  ["Поверхность", "surface", "#FFFFFF", "#161B22"],
  ["Вторичная поверхность", "surface-secondary", "#F8FAFC", "#1F2937"],
  ["Hover-поверхность", "surface-hover", "#F1F4F7", "#1C232D"],
  ["Основной текст", "text-primary", "#17212F", "#F0F3F6"],
  ["Вторичный текст", "text-secondary", "#667085", "#9AA4B2"],
  ["Третичный текст", "text-tertiary", "#98A2B3", "#6E7887"],
  ["Граница", "border", "#E5EAF0", "#303B49"],
  ["Бренд", "brand", "#176B55", "#38BFA0"],
  ["Бренд · subtle", "brand-subtle", "#EAF4F0", "#17302B"],
  ["Положительный", "positive", "#16865D", "#3CCB91"],
  ["Положительный · subtle", "positive-subtle", "#E7F5EE", "#17372F"],
  ["Отрицательный", "negative", "#D14B4B", "#F07878"],
  ["Отрицательный · subtle", "negative-subtle", "#FDEDED", "#3A2226"],
  ["Предупреждение", "warning", "#B7791F", "#E8B45B"],
  ["Предупреждение · subtle", "warning-subtle", "#FDF4E3", "#3A301C"],
  ["Информация", "info", "#4776C7", "#79A7F2"],
  ["Информация · subtle", "info-subtle", "#EBF1FB", "#1D2A40"],
  ["График 1", "chart-1", "#176B55", "#38BFA0"],
  ["График 2", "chart-2", "#4776C7", "#79A7F2"],
  ["График 3", "chart-3", "#D69A35", "#E8B45B"],
  ["График 4", "chart-4", "#7A6BD1", "#A99BF0"],
  ["График 5", "chart-5", "#98A2B3", "#6E7887"],
  ["Сетка графика", "chart-grid", "#EEF1F5", "#232B36"],
  ["Skeleton", "skeleton", "#EDF0F4", "#232B36"],
] as const;
const chartRows = [
  { month: "янв", income: 520000, expense: 390000 },
  { month: "фев", income: 520000, expense: 402000 },
  { month: "мар", income: 580000, expense: 410000 },
  { month: "апр", income: 580000, expense: 398000 },
  { month: "май", income: 600000, expense: 415000 },
  { month: "июн", income: 600000, expense: 405000 },
];
const chartPie = [
  { name: "Продукты", value: 118400, share: "28.68" },
  { name: "Кафе и рестораны", value: 71250, share: "17.26" },
  { name: "Жильё и коммунальные услуги", value: 48600, share: "11.77" },
  { name: "Транспорт", value: 21900, share: "5.30" },
];
const variants = [
  { key: "primary", label: "Primary" },
  { key: "secondary", label: "Secondary" },
  { key: "ghost", label: "Ghost" },
  { key: "danger", label: "Danger" },
];
const states = [
  { key: "", label: "Default" },
  { key: "preview-hover", label: "Hover" },
  { key: "preview-focus", label: "Focus" },
  { key: "disabled", label: "Disabled" },
  { key: "preview-loading", label: "Loading" },
];

function TokenGrid() {
  return (
    <section className="design-section">
      <h3>Цветовые токены · light / dark</h3>
      <p>
        Парные образцы показывают HEX для обеих тем. Токены напрямую связаны с CSS-переменными
        приложения.
      </p>
      <div className="token-grid">
        {tokenRows.map(([label, key, light, dark]) => (
          <article className="token-card card-surface" key={key}>
            <div className="token-pair">
              <div>
                <i style={{ background: `var(--${key})` }} />
                <small>Тема страницы</small>
                <code>{`var(--${key})`}</code>
              </div>
              <div>
                <i style={{ background: light }} />
                <small>Light</small>
                <code>{light}</code>
              </div>
              <div>
                <i style={{ background: dark }} />
                <small>Dark</small>
                <code>{dark}</code>
              </div>
            </div>
            <b>{label}</b>
          </article>
        ))}
      </div>
    </section>
  );
}

function ButtonGallery() {
  return (
    <section className="design-section">
      <h3>Кнопки · размер × состояние</h3>
      <div className="button-matrix card-surface">
        <div className="button-matrix-head">
          <span>Вариант / размер</span>
          {states.map((s) => (
            <span key={s.label}>{s.label}</span>
          ))}
        </div>
        {variants.flatMap((v) =>
          ["M", "S"].map((size) => (
            <div className="button-matrix-row" key={`${v.key}-${size}`}>
              <b>
                {v.label} · {size}
              </b>
              {states.map((state) => (
                <button
                  key={state.label}
                  disabled={state.key === "disabled" || state.key === "preview-loading"}
                  className={`button ${v.key} ${size === "S" ? "small" : ""} ${state.key}`}
                  aria-label={`${v.label}, ${size}, ${state.label}`}
                >
                  {state.key === "preview-loading" ? (
                    <>
                      <i className="spinner" /> Загрузка
                    </>
                  ) : state.label === "Default" ? (
                    "Действие"
                  ) : (
                    state.label
                  )}
                </button>
              ))}
            </div>
          )),
        )}
        <div className="button-row">
          <b>Дополнительно</b>
          <button className="icon-button" aria-label="Настройки">
            ⌘
          </button>
          <button className="button primary" onClick={() => toast.success("Изменения сохранены")}>
            Toast · успех
          </button>
          <button
            className="button secondary"
            onClick={() => toast.error("Не удалось выполнить действие")}
          >
            Toast · ошибка
          </button>
          <button className="button ghost" onClick={() => toast.info("Информационное сообщение")}>
            Toast · инфо
          </button>
        </div>
      </div>
    </section>
  );
}

function FormGallery() {
  const [segment, setSegment] = useState("Месяц");
  const [tab, setTab] = useState("Обзор");
  const [range, setRange] = useState("1–30 нояб. 2026");
  const [checked, setChecked] = useState(true);
  const [showFilter, setShowFilter] = useState(true);
  return (
    <section className="design-section">
      <h3>Поля, фильтры и выбор</h3>
      <div className="form-samples card-surface">
        <label>
          Поле ввода
          <input placeholder="Название операции" />
        </label>
        <label>
          Фокус
          <input className="preview-focus" placeholder="Фокус" />
        </label>
        <label>
          Ошибка
          <input aria-invalid="true" defaultValue="Неверное значение" />
        </label>
        <label>
          Отключено
          <input disabled defaultValue="Недоступно" />
        </label>
        <label>
          Сумма
          <div className="amount-field">
            <input defaultValue="125000,00" inputMode="decimal" />
            <span>₸</span>
          </div>
        </label>
        <label>
          Select
          <select defaultValue="kzt">
            <option value="kzt">KZT · ₸</option>
            <option>USD · $</option>
          </select>
        </label>
        <label>
          DatePicker
          <input type="date" defaultValue="2026-11-19" />
        </label>
        <label>
          Search
          <input type="search" placeholder="Найти операцию" />
        </label>
        <div className="full-field">
          <b className="sample-label">DateRange · пресеты</b>
          <input aria-label="Период дат" value={range} onChange={(e) => setRange(e.target.value)} />
          <div className="preset-row">
            {["7 дней", "Месяц", "Квартал", "Год"].map((x, i) => (
              <button
                className="button ghost small"
                key={x}
                onClick={() =>
                  setRange(
                    [
                      "13–19 нояб. 2026",
                      "1–30 нояб. 2026",
                      "1 сен. – 30 нояб. 2026",
                      "1 янв. – 31 дек. 2026",
                    ][i],
                  )
                }
              >
                {x}
              </button>
            ))}
          </div>
        </div>
        <div className="full-field">
          <b className="sample-label">SegmentedControl</b>
          <div className="segmented">
            {["Неделя", "Месяц", "Год"].map((x) => (
              <button
                className={segment === x ? "selected" : ""}
                key={x}
                onClick={() => setSegment(x)}
              >
                {x}
              </button>
            ))}
          </div>
        </div>
        <div className="full-field">
          <b className="sample-label">Tabs</b>
          <div className="tabs-sample" role="tablist">
            {["Обзор", "Операции", "Счета"].map((x) => (
              <button
                role="tab"
                aria-selected={tab === x}
                className={tab === x ? "selected" : ""}
                key={x}
                onClick={() => setTab(x)}
              >
                {x}
              </button>
            ))}
          </div>
        </div>
        <label className="check-sample">
          <input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} />{" "}
          Показывать архивные счета
        </label>
        <label className="check-sample">
          <input type="radio" name="demo-radio" defaultChecked /> KZT
        </label>
        <label className="check-sample">
          <input type="checkbox" role="switch" /> Включить уведомления
        </label>
        {showFilter && (
          <span className="filter-chip">
            Категория: Продукты{" "}
            <button aria-label="Удалить фильтр" onClick={() => setShowFilter(false)}>
              ×
            </button>
          </span>
        )}
      </div>
    </section>
  );
}

function ProgressExamples() {
  return (
    <div className="progress-examples card-surface">
      {[
        ["Норма", "54.75%", ""],
        ["Предупреждение", "82.57%", "warning"],
        ["Превышение", "118.75%", "exceeded"],
      ].map(([label, value, style]) => (
        <div key={label}>
          <b>{label}</b>
          <div className="progress-track">
            <i className={style} style={{ width: value }} />
          </div>
          <span>{value} · фактическое использование</span>
        </div>
      ))}
    </div>
  );
}

function SampleTable() {
  const rows = [
    {
      id: 1,
      description: "Покупка в магазине",
      category: "Продукты",
      date: "19.11.2026",
      amount: "12450.00",
      type: "expense",
    },
    {
      id: 2,
      description: "Зарплата ТОО «Демо»",
      category: "Зарплата",
      date: "19.11.2026",
      amount: "650000.00",
      type: "income",
    },
  ];

  return (
    <section className="design-section">
      <h3>Таблица · без сортируемых заголовков</h3>
      <div className="recent-card card-surface">
        <div className="table-scroll">
          <table className="transactions-table">
            <thead>
              <tr>
                <th>Операция</th>
                <th>Категория</th>
                <th>Дата</th>
                <th className="align-right">Сумма</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>{row.description}</td>
                  <td>{row.category}</td>
                  <td>{row.date}</td>
                  <td className="align-right tabular-nums">
                    {formatMoney(row.amount, "KZT", {
                      sign: row.type === "income" ? "+" : "−",
                    })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="pagination">
          <span>Показано 1–2 из 2</span>
          <div>
            <button className="button secondary small" disabled>
              Назад
            </button>
            <button className="button secondary small" disabled>
              Далее
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

function OverlayGallery() {
  const [dialog, setDialog] = useState(false);
  const [sheet, setSheet] = useState(false);
  const [menu, setMenu] = useState(false);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const sheetRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (dialog && dialogRef.current && !dialogRef.current.open) dialogRef.current.showModal();
  }, [dialog]);
  useEffect(() => {
    if (sheet && sheetRef.current && !sheetRef.current.open) sheetRef.current.showModal();
  }, [sheet]);
  return (
    <>
      <div className="dialog-sample">
        <button className="button secondary" onClick={() => setDialog(true)}>
          Dialog
        </button>
        <button className="button secondary" onClick={() => setSheet(true)}>
          Sheet
        </button>
        <div className="menu-demo">
          <button className="button secondary" aria-expanded={menu} onClick={() => setMenu(!menu)}>
            DropdownMenu
          </button>
          {menu && (
            <div className="demo-dropdown overlay-shadow" role="menu">
              <button
                role="menuitem"
                onClick={() => {
                  setMenu(false);
                  toast.info("Открыть операцию");
                }}
              >
                Открыть
              </button>
              <button
                role="menuitem"
                onClick={() => {
                  setMenu(false);
                  toast.success("Скопировано");
                }}
              >
                Копировать
              </button>
            </div>
          )}
        </div>
        <button className="button ghost" title="Подсказка: подсказка появляется при наведении">
          Tooltip
        </button>
      </div>
      {dialog && (
        <dialog
          ref={dialogRef}
          className="demo-dialog overlay-shadow"
          aria-labelledby="demo-dialog-title"
          onCancel={(e) => {
            e.preventDefault();
            setDialog(false);
          }}
        >
          <button
            className="overlay-close"
            aria-label="Закрыть диалог"
            onClick={() => setDialog(false)}
          >
            ×
          </button>
          <h3 id="demo-dialog-title">Подтвердите действие</h3>
          <p>Это пример модального окна с кратким подтверждением.</p>
          <div>
            <button className="button secondary" onClick={() => setDialog(false)}>
              Отмена
            </button>
            <button
              className="button primary"
              onClick={() => {
                setDialog(false);
                toast.success("Подтверждено");
              }}
            >
              Подтвердить
            </button>
          </div>
        </dialog>
      )}
      {sheet && (
        <dialog
          ref={sheetRef}
          className="demo-sheet overlay-shadow"
          aria-labelledby="demo-sheet-title"
          onCancel={(e) => {
            e.preventDefault();
            setSheet(false);
          }}
        >
          <button
            className="overlay-close"
            aria-label="Закрыть панель"
            onClick={() => setSheet(false)}
          >
            ×
          </button>
          <h3 id="demo-sheet-title">Параметры операции</h3>
          <p>Боковая панель · детали и действия</p>
          <button className="button primary" onClick={() => setSheet(false)}>
            Готово
          </button>
        </dialog>
      )}
    </>
  );
}

function ChartGallery() {
  return (
    <section className="design-section">
      <h3>Графики</h3>
      <div className="design-charts">
        <ChartCard title="Столбцы · доход / расход">
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartRows}>
                <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                <XAxis dataKey="month" />
                <YAxis tickFormatter={(v) => `${Math.round(Number(v) / 1000)}k`} />
                <Tooltip
                  formatter={(v) => formatMoney(String(v), "KZT", { hideZeroCents: true })}
                />
                <Bar dataKey="income" name="Доход" fill="var(--chart-1)" radius={[4, 4, 0, 0]} />
                <Bar dataKey="expense" name="Расход" fill="var(--chart-2)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </ChartCard>
        <ChartCard title="Линия">
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartRows}>
                <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                <XAxis dataKey="month" />
                <YAxis tickFormatter={(v) => `${Math.round(Number(v) / 1000)}k`} />
                <Tooltip
                  formatter={(v) => formatMoney(String(v), "KZT", { hideZeroCents: true })}
                />
                <Line
                  dataKey="income"
                  name="Доход"
                  stroke="var(--chart-1)"
                  strokeWidth={2.5}
                  dot={false}
                />
                <Line
                  dataKey="expense"
                  name="Расход"
                  stroke="var(--chart-2)"
                  strokeWidth={2.5}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </ChartCard>
        <ChartCard title="Donut · сумма и доля">
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={chartPie}
                  dataKey="value"
                  nameKey="name"
                  innerRadius="55%"
                  outerRadius="82%"
                >
                  {chartPie.map((_, i) => (
                    <Cell key={i} fill={`var(--chart-${(i % 5) + 1})`} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(v) => formatMoney(String(v), "KZT", { hideZeroCents: true })}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="legend">
            {chartPie.map((row, i) => (
              <div className="legend-row" key={row.name}>
                <span className="legend-name">
                  <i style={{ background: `var(--chart-${(i % 5) + 1})` }} />
                  {row.name}
                </span>
                <b>
                  {formatMoney(String(row.value), "KZT", {
                    hideZeroCents: true,
                  })}
                </b>
                <span>{formatPercent(row.share)}</span>
              </div>
            ))}
          </div>
        </ChartCard>
      </div>
    </section>
  );
}

export default function DesignSystemShowcase() {
  const [segment, setSegment] = useState("Месяц");
  const [tab, setTab] = useState("Обзор");
  return (
    <div className="design-page">
      <div className="design-intro">
        <div>
          <span className="overline">КОМПОНЕНТЫ И ТОКЕНЫ</span>
          <h2>Дизайн-система</h2>
          <p>Библиотека интерфейса BudgetAnalytics для светлой и тёмной тем.</p>
        </div>
        <BackendBadge />
      </div>
      <TokenGrid />
      <StateSections />
      <section className="design-section">
        <h3>Типографика и геометрия</h3>
        <div className="type-specimens card-surface">
          <div>
            <span className="overline">H1 · 24 / 30 · BOLD</span>
            <h1>Обзор финансов</h1>
          </div>
          <div>
            <span className="overline">H2 · 18 / 24 · SEMIBOLD</span>
            <h2>Структура расходов</h2>
          </div>
          <div>
            <span className="overline">H3 · 15 / 20 · SEMIBOLD</span>
            <h3>Последние операции</h3>
          </div>
          <div>
            <span className="overline">BODY · 14 / 20</span>
            <p>Основной текст интерфейса и описания элементов.</p>
          </div>
          <div>
            <span className="overline">ТАБЛИЧНЫЕ ЧИСЛА</span>
            <p className="tabular-nums">1 250 000,50 ₸ · 80,00 %</p>
          </div>
          <div>
            <span className="overline">ОТСТУПЫ · 4PX GRID / RADIUS</span>
            <p>Шкала: 4 · 8 · 12 · 16 · 24 · 32 px; радиусы: 6 · 8 · 12 · 16 px.</p>
          </div>
        </div>
      </section>
      <ButtonGallery />
      <FormGallery />
      <section className="design-section">
        <h3>Компоненты шагов 2–6</h3>
        <div className="feature-gallery-grid">
          <article className="feature-sample card-surface">
            <h4>Фильтр-чипы</h4>
            <div className="feature-chip-row">
              <span>
                Категория: Кафе <b>×</b>
              </span>
              <span>
                Период: Ноябрь <b>×</b>
              </span>
              <span>
                Счёт: Kaspi <b>×</b>
              </span>
            </div>
          </article>
          <article className="feature-sample card-surface">
            <h4>Мастер шагов</h4>
            <div className="feature-stepper">
              <span className="complete">1 · Файл</span>
              <i />
              <span className="current">2 · Проверка</span>
              <i />
              <span>3 · Импорт</span>
            </div>
          </article>
          <article className="feature-sample card-surface">
            <h4>Статусы строк импорта</h4>
            <div className="feature-status-row">
              <StatusBadge tone="positive">Корректная</StatusBadge>
              <StatusBadge tone="warning">Возможный дубль</StatusBadge>
              <StatusBadge tone="negative">Ошибка</StatusBadge>
              <StatusBadge tone="info">Импортирована</StatusBadge>
            </div>
          </article>
          <article className="feature-sample card-surface">
            <h4>Карточка ответа AI</h4>
            <div className="feature-ai-card">
              <b>AI · Данные на 19.11.2026</b>
              <p>Сверьте расходы по категории с бюджетом.</p>
              <small>На чём основан ответ · F1, F2</small>
            </div>
          </article>
          <article className="feature-sample card-surface">
            <h4>Доступность функции</h4>
            <BackendBadge />
          </article>
        </div>
      </section>
      <section className="design-section">
        <h3>Бейджи, карточки и метрики</h3>
        <div className="badge-samples card-surface">
          {(["positive", "negative", "warning", "info", "neutral"] as const).map((tone, i) => (
            <StatusBadge key={tone} tone={tone}>
              {["Положительно", "Отрицательно", "Предупреждение", "Информация", "Нейтрально"][i]}
            </StatusBadge>
          ))}
          <BackendBadge />
          <span className="card-sample card-surface">Карточка без тени</span>
        </div>
        <div className="metrics-grid design-metrics">
          <MetricCard
            label="Баланс счетов"
            value="1 723 821 ₸"
            change="2.40"
            caption="к прошлому месяцу"
          />
          <MetricCard label="Загрузка" value="" loading />
          <MetricCard label="Пустое значение" value="—" caption="Нет данных за период" />
        </div>
        <ProgressExamples />
      </section>
      <SampleTable />
      <ChartGallery />
      <section className="design-section">
        <h3>Состояния, баннеры и уведомления</h3>
        <div className="state-examples">
          <div className="card-surface">
            <EmptyState
              description="Добавьте первую операцию, чтобы увидеть данные."
              action={<button className="button primary">Добавить операцию</button>}
            />
          </div>
          <div className="card-surface">
            <ErrorState retry={() => toast.info("Запрос повторён")} />
          </div>
          <div className="card-surface skeleton-sample">
            <SkeletonCard />
          </div>
        </div>
        <div className="banners">
          <div className="banner info">Информация: данные отображаются в демо-режиме.</div>
          <div className="banner warning">Предупреждение: бюджет почти исчерпан.</div>
          <div className="banner error">Ошибка: не удалось обновить сведения.</div>
        </div>
        <div className="demo-controls">
          <div className="segmented">
            {["Неделя", "Месяц", "Год"].map((x) => (
              <button
                className={segment === x ? "selected" : ""}
                key={x}
                onClick={() => setSegment(x)}
              >
                {x}
              </button>
            ))}
          </div>
          <div className="tabs-sample" role="tablist">
            {["Обзор", "Операции", "Счета"].map((x) => (
              <button
                role="tab"
                aria-selected={tab === x}
                className={tab === x ? "selected" : ""}
                key={x}
                onClick={() => setTab(x)}
              >
                {x}
              </button>
            ))}
          </div>
          <button className="button primary" onClick={() => toast.success("Действие выполнено")}>
            Успешное уведомление
          </button>
        </div>
        <OverlayGallery />
      </section>
    </div>
  );
}
