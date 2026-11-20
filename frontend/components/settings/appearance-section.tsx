"use client";

import { useSyncExternalStore } from "react";
import { useTheme } from "next-themes";
import { Check, Monitor, Moon, Sun } from "lucide-react";

const THEME_OPTIONS = [
  { value: "light", label: "Светлая", Icon: Sun },
  { value: "dark", label: "Тёмная", Icon: Moon },
  { value: "system", label: "Как в системе", Icon: Monitor },
] as const;

const noopSubscribe = () => () => {};

export function AppearanceSection() {
  const { theme, setTheme } = useTheme();
  // next-themes knows the stored theme only on the client; avoid a hydration mismatch.
  const mounted = useSyncExternalStore(
    noopSubscribe,
    () => true,
    () => false,
  );
  const current = mounted ? theme : undefined;
  return (
    <section className="settings-section-content" aria-labelledby="settings-appearance-title">
      <div className="settings-section-heading">
        <div>
          <h2 id="settings-appearance-title">Оформление</h2>
          <p>Тема и язык интерфейса</p>
        </div>
      </div>
      <fieldset className="settings-theme-fieldset">
        <legend>Тема</legend>
        <div className="settings-theme-options">
          {THEME_OPTIONS.map(({ value, label, Icon }) => (
            <button
              type="button"
              className={`settings-theme-option card-surface ${current === value ? "selected" : ""}`}
              aria-pressed={current === value}
              key={value}
              onClick={() => setTheme(value)}
            >
              <span className={`settings-theme-preview ${value}`}>
                <i />
                <i />
                <i />
              </span>
              <span className="settings-theme-label">
                <Icon aria-hidden="true" /> {label}
              </span>
              {current === value && <Check className="settings-theme-check" aria-hidden="true" />}
            </button>
          ))}
        </div>
      </fieldset>
      <div className="settings-option-card card-surface">
        <div>
          <h3>
            <label htmlFor="settings-language">Язык</label>
          </h3>
          <p>Другие языки пока недоступны</p>
        </div>
        <select id="settings-language" value="ru" disabled>
          <option value="ru">Русский</option>
          <option value="kk" disabled>
            Қазақша
          </option>
          <option value="en" disabled>
            English
          </option>
        </select>
      </div>
      <p className="settings-browser-note">Настройки оформления хранятся в этом браузере</p>
    </section>
  );
}
