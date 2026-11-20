"use client";

import { useCallback, useState } from "react";
import { toast } from "sonner";
import { changePassword, logoutAll } from "@/lib/api/client";
import { ApiError, toUserMessage } from "@/lib/api/errors";
import { BackendFeature } from "./backend-feature";
import { ConfirmDialog } from "./confirm-dialog";
import "./settings.css";
import { navigateWithFullReload } from "@/lib/navigation";

export const PASSWORD_MIN = 8;
export const PASSWORD_MAX = 128;
export const PASSWORD_CHANGED_MESSAGE = "Пароль изменён. Все сессии завершены — войдите снова";

type PasswordErrors = { current?: string; next?: string; confirm?: string; form?: string };

function validate(current: string, next: string, confirm: string): PasswordErrors {
  const errors: PasswordErrors = {};
  if (!current) errors.current = "Введите текущий пароль";
  if (next.length < PASSWORD_MIN || next.length > PASSWORD_MAX) {
    errors.next = `Пароль должен быть от ${PASSWORD_MIN} до ${PASSWORD_MAX} символов`;
  }
  if (next !== confirm) errors.confirm = "Пароли не совпадают";
  return errors;
}

function errorsFromApi(error: unknown): PasswordErrors {
  if (error instanceof ApiError) {
    if (error.code === "wrong_password") return { current: "Неверный текущий пароль" };
    const mapped: PasswordErrors = {};
    for (const issue of error.fieldErrors) {
      if (issue.field === "old_password") mapped.current = issue.message;
      else if (issue.field === "new_password") mapped.next = issue.message;
    }
    if (mapped.current || mapped.next) return mapped;
  }
  return { form: toUserMessage(error) };
}

function PasswordField({
  id,
  label,
  autoComplete,
  value,
  onChange,
  error,
  hint,
}: {
  id: string;
  label: string;
  autoComplete: "current-password" | "new-password";
  value: string;
  onChange: (value: string) => void;
  error?: string;
  hint?: string;
}) {
  const messageId = `${id}-message`;
  return (
    <div className="settings-password-field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="password"
        autoComplete={autoComplete}
        maxLength={PASSWORD_MAX}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={Boolean(error)}
        aria-describedby={error || hint ? messageId : undefined}
      />
      {error ? (
        <span id={messageId} className="settings-field-error">
          {error}
        </span>
      ) : (
        hint && <small id={messageId}>{hint}</small>
      )}
    </div>
  );
}

function PasswordForm() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<PasswordErrors>({});
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found = validate(current, next, confirm);
    setErrors(found);
    if (Object.keys(found).length) return;
    setBusy(true);
    try {
      await changePassword({ old_password: current, new_password: next });
      // The server proxy has already cleared the session cookies.
      setDone(true);
      toast.success(PASSWORD_CHANGED_MESSAGE);
      navigateWithFullReload("/login");
    } catch (error) {
      setErrors(errorsFromApi(error));
      setBusy(false);
    }
  }

  return (
    <form className="settings-password-form card-surface" onSubmit={submit} noValidate>
      <h3>Сменить пароль</h3>
      <PasswordField
        id="settings-current-password"
        label="Текущий пароль"
        autoComplete="current-password"
        value={current}
        onChange={setCurrent}
        error={errors.current}
      />
      <PasswordField
        id="settings-new-password"
        label="Новый пароль"
        autoComplete="new-password"
        value={next}
        onChange={setNext}
        error={errors.next}
        hint={`От ${PASSWORD_MIN} до ${PASSWORD_MAX} символов`}
      />
      <PasswordField
        id="settings-confirm-password"
        label="Повторите новый пароль"
        autoComplete="new-password"
        value={confirm}
        onChange={setConfirm}
        error={errors.confirm}
      />
      {errors.form && (
        <p className="settings-field-error" role="alert">
          {errors.form}
        </p>
      )}
      {done && <p role="status">{PASSWORD_CHANGED_MESSAGE}</p>}
      <p className="settings-browser-note">
        После смены пароля все сессии будут завершены, потребуется войти снова.
      </p>
      <button className="button primary" type="submit" disabled={busy}>
        {busy ? "Сохраняю…" : "Изменить пароль"}
      </button>
    </form>
  );
}

function LogoutAllBlock() {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const close = useCallback(() => {
    setOpen(false);
    setError("");
  }, []);

  async function confirmLogout() {
    setBusy(true);
    setError("");
    try {
      await logoutAll();
      navigateWithFullReload("/login");
    } catch (requestError) {
      setError(toUserMessage(requestError));
      setBusy(false);
    }
  }

  return (
    <div className="settings-security-actions card-surface">
      <div>
        <h3>Сеансы</h3>
        <p>Завершить все активные сеансы этого аккаунта, включая текущий</p>
      </div>
      <button type="button" className="button secondary" onClick={() => setOpen(true)}>
        Выйти на всех устройствах
      </button>
      {open && (
        <ConfirmDialog
          title="Выйти на всех устройствах?"
          description="Все сессии, включая текущую, будут завершены. Потребуется войти снова."
          confirmLabel="Выйти"
          busy={busy}
          error={error}
          onConfirm={() => void confirmLogout()}
          onCancel={close}
        />
      )}
    </div>
  );
}

export function SecuritySection() {
  return (
    <section className="settings-section-content" aria-labelledby="settings-security-title">
      <div className="settings-section-heading">
        <div>
          <h2 id="settings-security-title">Безопасность</h2>
          <p>Пароль и доступ к аккаунту</p>
        </div>
      </div>
      <PasswordForm />
      <LogoutAllBlock />
      <div className="settings-backend-list">
        <BackendFeature
          title="Активные сессии"
          description="Просмотр устройств и завершение отдельных сеансов."
        />
        <BackendFeature
          title="Двухфакторная аутентификация"
          description="Дополнительная защита при входе в аккаунт."
        />
        <BackendFeature
          title="Удаление аккаунта и экспорт данных"
          description="Запросить архив данных или удалить аккаунт."
        />
      </div>
    </section>
  );
}
