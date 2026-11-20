"use client";

/**
 * Design-system showcase sections added for the production release:
 * component state matrix, accordion, responsive navigation and a light/dark
 * comparison. Everything here is a static example; no data comes from the API.
 */
import {
  ChevronDown,
  LayoutDashboard,
  ListChecks,
  MoreHorizontal,
  Plus,
  Settings,
  Wallet,
  X,
} from "lucide-react";

import "./design-system.css";

const STATES = ["Default", "Hover", "Focus", "Disabled", "Error"] as const;
type State = (typeof STATES)[number];

const stateClass: Record<State, string> = {
  Default: "",
  Hover: "ds-force-hover",
  Focus: "ds-force-focus",
  Disabled: "",
  Error: "ds-force-error",
};

function StateMatrix() {
  return (
    <section className="design-section" aria-labelledby="ds-state-matrix">
      <h3 id="ds-state-matrix">Матрица состояний</h3>
      <p className="ds-note">
        Hover и Focus показаны статически (классами-имитаторами); в интерфейсе они возникают при
        наведении и при навигации с клавиатуры.
      </p>
      <div className="ds-matrix" role="table" aria-label="Состояния компонентов">
        <div className="ds-matrix-row ds-matrix-head" role="row">
          <span role="columnheader">Компонент</span>
          {STATES.map((state) => (
            <span role="columnheader" key={state}>
              {state}
            </span>
          ))}
        </div>
        <div className="ds-matrix-row" role="row">
          <span role="rowheader">Кнопка primary</span>
          {STATES.map((state) => (
            <span role="cell" key={state}>
              {state === "Error" ? (
                <span className="ds-na">—</span>
              ) : (
                <button
                  type="button"
                  className={`button primary ${stateClass[state]}`}
                  disabled={state === "Disabled"}
                  tabIndex={-1}
                >
                  Сохранить
                </button>
              )}
            </span>
          ))}
        </div>
        <div className="ds-matrix-row" role="row">
          <span role="rowheader">Поле суммы</span>
          {STATES.map((state) => (
            <span role="cell" key={state}>
              <span className={`ds-field ${stateClass[state]}`}>
                <input
                  aria-label={`Сумма — ${state}`}
                  defaultValue={state === "Error" ? "0" : "12 500,00"}
                  disabled={state === "Disabled"}
                  aria-invalid={state === "Error"}
                  tabIndex={-1}
                  readOnly
                />
                <span aria-hidden="true">₸</span>
              </span>
              {state === "Error" && (
                <small className="ds-error-text">Укажите сумму больше нуля</small>
              )}
            </span>
          ))}
        </div>
        <div className="ds-matrix-row" role="row">
          <span role="rowheader">Фильтр-чип</span>
          {STATES.map((state) => (
            <span role="cell" key={state}>
              {state === "Error" ? (
                <span className="ds-na">—</span>
              ) : (
                <span
                  className={`filter-chip ${stateClass[state]} ${state === "Disabled" ? "ds-disabled" : ""}`}
                >
                  Категория: Продукты
                  <button
                    type="button"
                    aria-label="Убрать фильтр"
                    disabled={state === "Disabled"}
                    tabIndex={-1}
                  >
                    <X size={12} aria-hidden="true" />
                  </button>
                </span>
              )}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}

function AccordionExample() {
  return (
    <section className="design-section" aria-labelledby="ds-accordion">
      <h3 id="ds-accordion">Аккордеон</h3>
      <p className="ds-note">
        Используется на mobile в финансовом отчёте AI. Нативные &lt;details&gt;/&lt;summary&gt;:
        работают с клавиатуры и скринридером без дополнительного JS.
      </p>
      <div className="ds-accordion">
        {[
          ["Наблюдения", "Расходы на кафе выросли относительно прошлого месяца (пример)."],
          ["Рекомендации", "Установите бюджет на категорию «Кафе и рестораны» (пример)."],
          ["Риски", "Подушка безопасности покрывает меньше трёх месяцев расходов (пример)."],
        ].map(([title, body], index) => (
          <details key={title} open={index === 0}>
            <summary>
              {title}
              <ChevronDown size={16} aria-hidden="true" />
            </summary>
            <p>{body}</p>
          </details>
        ))}
      </div>
    </section>
  );
}

function NavigationExample() {
  const items = [
    { icon: LayoutDashboard, label: "Обзор", active: true },
    { icon: ListChecks, label: "Операции" },
    { icon: Wallet, label: "Счета" },
    { icon: Settings, label: "Настройки" },
  ];
  return (
    <section className="design-section" aria-labelledby="ds-navigation">
      <h3 id="ds-navigation">Адаптивная навигация</h3>
      <div className="ds-nav-grid">
        <figure>
          <figcaption>Desktop ≥ 1200 px · сайдбар 248 px</figcaption>
          <div className="ds-nav-sidebar" aria-hidden="true">
            {items.map((item) => (
              <span key={item.label} className={item.active ? "active" : ""}>
                <item.icon size={16} /> {item.label}
              </span>
            ))}
          </div>
        </figure>
        <figure>
          <figcaption>Tablet 768–1199 px · рейка 72 px</figcaption>
          <div className="ds-nav-rail" aria-hidden="true">
            {items.map((item) => (
              <span key={item.label} className={item.active ? "active" : ""} title={item.label}>
                <item.icon size={18} />
              </span>
            ))}
          </div>
        </figure>
        <figure>
          <figcaption>Mobile &lt; 768 px · нижняя панель</figcaption>
          <div className="ds-nav-bottom" aria-hidden="true">
            <span className="active">
              <LayoutDashboard size={18} /> Обзор
            </span>
            <span>
              <ListChecks size={18} /> Операции
            </span>
            <span className="ds-nav-plus">
              <Plus size={18} />
            </span>
            <span>
              <Wallet size={18} /> Аналитика
            </span>
            <span>
              <MoreHorizontal size={18} /> Ещё
            </span>
          </div>
        </figure>
      </div>
    </section>
  );
}

function ThemeSample() {
  return (
    <div className="ds-theme-sample card-surface">
      <span className="overline">БАЛАНС СЧЕТОВ</span>
      <strong>1 723 820 ₸</strong>
      <span className="ds-theme-positive">+12 500,00 ₸</span>
      <span className="ds-theme-negative">Превышен на 11 250,00 ₸</span>
      <button type="button" className="button primary" tabIndex={-1}>
        Добавить операцию
      </button>
    </div>
  );
}

function ThemeComparison() {
  return (
    <section className="design-section" aria-labelledby="ds-themes">
      <h3 id="ds-themes">Light и Dark · одна структура</h3>
      <div className="ds-theme-pair">
        <div className="ds-theme-light">
          <small>Light</small>
          <ThemeSample />
        </div>
        <div className="dark ds-theme-dark">
          <small>Dark · Graphite + Teal</small>
          <ThemeSample />
        </div>
      </div>
    </section>
  );
}

export function StateSections() {
  return (
    <>
      <StateMatrix />
      <ThemeComparison />
      <AccordionExample />
      <NavigationExample />
    </>
  );
}
