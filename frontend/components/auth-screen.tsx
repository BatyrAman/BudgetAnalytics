"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { login, register } from "@/lib/api/client";
import { ApiError, toUserMessage } from "@/lib/api/errors";
import { ChartNoAxesCombined, CircleDollarSign, ShieldCheck, Wallet } from "lucide-react";
import { BackendBadge } from "./common";
import { navigateWithFullReload } from "@/lib/navigation";

type Mode = "login" | "register" | "forgot" | "reset";

const titles: Record<Mode, string> = {
  login: "С возвращением",
  register: "Создайте аккаунт",
  forgot: "Восстановление пароля",
  reset: "Новый пароль",
};

const descriptions: Record<Mode, string> = {
  login: "Войдите, чтобы продолжить работу с финансами",
  register: "Начните управлять личными финансами",
  forgot: "Укажите e-mail, связанный с аккаунтом",
  reset: "Придумайте новый пароль для аккаунта",
};

export function AuthScreen({ mode }: { mode: Mode }) {
  const [error, setError] = useState("");
  const [rateLimit, setRateLimit] = useState(false);
  const [seconds, setSeconds] = useState(30);
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const searchParams = useSearchParams();
  const recoveryNeedsBackend = mode === "forgot" || mode === "reset";

  useEffect(() => {
    if (!rateLimit) return;
    const timer = window.setInterval(() => {
      setSeconds((remaining) => {
        if (remaining <= 1) {
          window.clearInterval(timer);
          setRateLimit(false);
          return 30;
        }
        return remaining - 1;
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [rateLimit]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (rateLimit || submitting || recoveryNeedsBackend) return;
    const values = new FormData(event.currentTarget);
    const password = String(values.get("password") ?? "");

    if (mode === "register" && password !== values.get("confirm-password")) {
      setError("Пароли не совпадают");
      return;
    }

    setSubmitting(true);
    try {
      if (mode === "login") {
        await login({ email: email.trim(), password });
      } else {
        await register({
          full_name: String(values.get("name") ?? "").trim(),
          email: email.trim(),
          password,
        });
      }
      navigateWithFullReload(safeNextPath(searchParams.get("next")));
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 429) {
        setSeconds(caught.retryAfterSeconds ?? 30);
        setRateLimit(true);
      } else {
        setError(toUserMessage(caught));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-layout">
      <aside className="auth-aside">
        <Link href="/dashboard" className="brand-lockup" prefetch={false}>
          <span className="brand-mark">
            <Wallet />
          </span>
          <span>
            Budget<span className="brand-light">Analytics</span>
          </span>
        </Link>
        <div className="auth-pitch">
          <span className="overline">ЛИЧНЫЕ ФИНАНСЫ — ПРОЗРАЧНО</span>
          <h1>Деньги под контролем. Решения — увереннее.</h1>
          <p>Соберите счета, расходы и цели в одном понятном обзоре.</p>
          <ul>
            <li>
              <span>
                <ChartNoAxesCombined />
              </span>
              <div>
                <b>Целостная картина</b>
                <small>Доходы, расходы и баланс в одном месте</small>
              </div>
            </li>
            <li>
              <span>
                <ShieldCheck />
              </span>
              <div>
                <b>Понятные бюджеты</b>
                <small>Отслеживайте лимиты без сложных таблиц</small>
              </div>
            </li>
            <li>
              <span>
                <CircleDollarSign />
              </span>
              <div>
                <b>Цели и накопления</b>
                <small>Двигайтесь к важному шаг за шагом</small>
              </div>
            </li>
          </ul>
        </div>
      </aside>

      <section className="auth-main" aria-labelledby="auth-title">
        <div className="auth-mobile-brand">
          <span className="brand-mark">
            <Wallet />
          </span>
          BudgetAnalytics
        </div>
        <div className="auth-form-wrap">
          <span className="overline">ЛИЧНЫЙ КАБИНЕТ</span>
          <h2 id="auth-title">{titles[mode]}</h2>
          <p className="auth-description">{descriptions[mode]}</p>
          {recoveryNeedsBackend && (
            <div className="backend-banner">
              <BackendBadge />
              <span>Восстановление пароля пока недоступно — требует backend</span>
            </div>
          )}
          {error && (
            <div className="form-error" role="alert">
              {error}
            </div>
          )}
          {rateLimit && (
            <div className="form-error" role="alert">
              Слишком много попыток. Повторите через {formatCountdown(seconds)}
            </div>
          )}

          <form onSubmit={submit} className="auth-form">
            {mode === "register" && (
              <label>
                Имя
                <input
                  name="name"
                  required
                  minLength={2}
                  autoComplete="name"
                  placeholder="Ваше имя"
                />
              </label>
            )}
            {mode !== "reset" && (
              <label>
                E-mail
                <input
                  name="email"
                  required
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  autoComplete="email"
                  placeholder="name@example.kz"
                />
              </label>
            )}
            {(mode === "login" || mode === "register" || mode === "reset") && (
              <label>
                Пароль
                <input
                  name="password"
                  required
                  type="password"
                  minLength={mode === "register" ? 8 : 1}
                  maxLength={128}
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  placeholder={mode === "register" ? "Не менее 8 символов" : "Введите пароль"}
                  aria-describedby={mode === "register" ? "password-hint" : undefined}
                />
              </label>
            )}
            {mode === "register" && (
              <small id="password-hint" className="field-hint">
                От 8 до 128 символов
              </small>
            )}
            {mode === "register" && (
              <label>
                Подтвердите пароль
                <input
                  name="confirm-password"
                  required
                  type="password"
                  minLength={8}
                  maxLength={128}
                  autoComplete="new-password"
                  placeholder="Повторите пароль"
                />
              </label>
            )}
            {mode === "login" && (
              <div className="forgot-row">
                <Link href="/forgot-password">Забыли пароль?</Link>
              </div>
            )}
            <button
              className="button primary auth-submit"
              type="submit"
              disabled={recoveryNeedsBackend || rateLimit || submitting}
              aria-busy={submitting}
            >
              {mode === "login"
                ? "Войти"
                : mode === "register"
                  ? "Создать аккаунт"
                  : mode === "forgot"
                    ? "Отправить ссылку"
                    : "Сохранить пароль"}
            </button>
          </form>

          {mode === "login" ? (
            <p className="auth-switch">
              Нет аккаунта? <Link href="/register">Создать аккаунт</Link>
            </p>
          ) : mode === "register" ? (
            <p className="auth-switch">
              Уже есть аккаунт? <Link href="/login">Войти</Link>
            </p>
          ) : (
            <p className="auth-switch">
              <Link href="/login">Вернуться ко входу</Link>
            </p>
          )}
        </div>
      </section>
    </main>
  );
}

/** Only same-site relative paths are accepted after login (no open redirect). */
export function safeNextPath(next: string | null): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) {
    return "/dashboard";
  }
  return next;
}

function formatCountdown(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}
