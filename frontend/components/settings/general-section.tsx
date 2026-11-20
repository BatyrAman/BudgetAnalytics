"use client";

import { useState } from "react";
import { useSWRConfig } from "swr";
import { BackendBadge, ErrorState, Skeleton } from "@/components/common";
import { DEFAULT_TIMEZONE, TIMEZONE_STORAGE_KEY, setTimezone, useTimezone } from "@/lib/timezone";
import { useMe } from "@/lib/api/hooks";
import { formatDate } from "@/lib/format";

/** localStorage key read by `lib/api/client.ts` (`currentTimezone`). */
export { TIMEZONE_STORAGE_KEY };

export const TIMEZONES = [
  ["Asia/Almaty", "Алматы"],
  ["Asia/Aqtobe", "Актобе"],
  ["Asia/Qyzylorda", "Кызылорда"],
  ["Asia/Oral", "Уральск"],
  ["Asia/Atyrau", "Атырау"],
] as const;

function ProfileCard() {
  const { data: user, error, isLoading, mutate } = useMe();
  return (
    <div className="settings-profile-card card-surface">
      {isLoading ? (
        <div aria-label="Загрузка профиля">
          <Skeleton className="short" />
          <Skeleton className="medium" />
        </div>
      ) : error ? (
        <ErrorState
          error={error}
          retry={() => void mutate()}
          title="Не удалось загрузить профиль"
        />
      ) : (
        user && (
          <dl>
            <div>
              <dt>Имя</dt>
              <dd>{user.full_name}</dd>
            </div>
            <div>
              <dt>E-mail</dt>
              <dd>{user.email}</dd>
            </div>
            <div>
              <dt>Дата регистрации</dt>
              <dd>{formatDate(user.created_at)}</dd>
            </div>
          </dl>
        )
      )}
      <div className="settings-profile-action">
        <span title="Требует backend">
          <button type="button" className="button secondary" disabled>
            Изменить профиль
          </button>
        </span>
        <BackendBadge />
      </div>
    </div>
  );
}

export function GeneralSection() {
  const { mutate } = useSWRConfig();
  const { data: user } = useMe();
  // localStorage is unavailable during server rendering: the server snapshot is the default.
  const timezone = useTimezone() ?? DEFAULT_TIMEZONE;
  const [saveError, setSaveError] = useState("");

  function changeTimezone(value: string) {
    try {
      setTimezone(value);
      setSaveError("");
    } catch {
      setSaveError("Не удалось сохранить часовой пояс в этом браузере.");
      return;
    }
    // Period boundaries depend on the time zone: refetch every cached request.
    void mutate(() => true);
  }

  const options = TIMEZONES.some(([value]) => value === timezone)
    ? TIMEZONES
    : [...TIMEZONES, [timezone, timezone] as const];

  return (
    <section className="settings-section-content" aria-labelledby="settings-general-title">
      <div className="settings-section-heading">
        <div>
          <h2 id="settings-general-title">Общие</h2>
          <p>Профиль и параметры приложения</p>
        </div>
      </div>
      <ProfileCard />
      <div className="settings-option-card card-surface">
        <div>
          <h3>Валюта по умолчанию</h3>
          <p>Изменение валюты по умолчанию требует доработки backend</p>
        </div>
        <strong className="settings-static-value">{user?.default_currency_code ?? "—"}</strong>
        <BackendBadge />
      </div>
      <div className="settings-option-card card-surface">
        <div>
          <h3>
            <label htmlFor="settings-timezone">Часовой пояс</label>
          </h3>
          <p>Сохраняется в этом браузере</p>
          {saveError && (
            <p className="settings-field-error" role="alert">
              {saveError}
            </p>
          )}
        </div>
        <select
          id="settings-timezone"
          value={timezone}
          onChange={(event) => changeTimezone(event.target.value)}
        >
          {options.map(([value, label]) => (
            <option value={value} key={value}>
              {value.replace("Asia/", "")} · {label}
            </option>
          ))}
        </select>
      </div>
    </section>
  );
}
