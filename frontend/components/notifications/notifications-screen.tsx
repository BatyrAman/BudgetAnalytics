"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Bell, CheckCheck, CheckCircle2, ChevronRight, X } from "lucide-react";
import { BackendBadge, EmptyState, StatusBadge } from "@/components/common";
import { PREVIEW_ENABLED } from "@/lib/preview";
import "./notifications.css";
import { EXAMPLE_NOTIFICATIONS, type ExampleNotification } from "./notification-examples";

function NotificationSheet({
  notification,
  onClose,
}: {
  notification: ExampleNotification;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div
      className="notification-sheet-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        className="notification-sheet card-surface"
        role="dialog"
        aria-modal="true"
        aria-labelledby="notification-sheet-title"
      >
        <div className="notification-sheet-head">
          <span className="notification-icon">
            <notification.Icon aria-hidden="true" />
          </span>
          <button type="button" onClick={onClose} aria-label="Закрыть подробности" autoFocus>
            <X aria-hidden="true" />
          </button>
        </div>
        <StatusBadge tone="neutral">Пример</StatusBadge>
        <h2 id="notification-sheet-title">{notification.title}</h2>
        <p>{notification.body}</p>
        <p>{notification.when}</p>
        <Link href={notification.href} className="button primary" onClick={onClose}>
          {notification.entityLabel}
          <ChevronRight aria-hidden="true" />
        </Link>
        <p className="notification-sheet-note">
          <CheckCircle2 aria-hidden="true" /> Демонстрационный макет — уведомление не сохранено.
        </p>
      </section>
    </div>
  );
}

export function NotificationsScreen() {
  const [showExamples, setShowExamples] = useState(false);
  const [selected, setSelected] = useState<ExampleNotification | null>(null);
  const examplesVisible = PREVIEW_ENABLED && showExamples;
  return (
    <section className="notifications-page">
      <header className="notifications-heading">
        <div>
          <h2>Уведомления</h2>
          <p>События, связанные с вашими финансами</p>
        </div>
        <BackendBadge />
      </header>
      <div className="notifications-warning" role="note">
        <Bell aria-hidden="true" />
        <p>Уведомления пока не поддерживаются backend — экран показывает планируемый дизайн</p>
      </div>
      <div className="notifications-actions">
        <span title="Требует backend">
          <button type="button" className="button secondary small" disabled>
            <CheckCheck aria-hidden="true" /> Отметить всё прочитанным
          </button>
        </span>
      </div>
      {PREVIEW_ENABLED && (
        <label className="notifications-demo-switch">
          <span>
            <strong>Демо: макет списка</strong>
            <small>Показывает примеры, а не реальные уведомления</small>
          </span>
          <input
            type="checkbox"
            role="switch"
            checked={showExamples}
            onChange={(event) => setShowExamples(event.target.checked)}
          />
        </label>
      )}
      {!examplesVisible ? (
        <div className="notifications-empty card-surface">
          <EmptyState
            title="Уведомлений пока нет"
            description="Когда backend будет готов, здесь появятся события и напоминания."
          />
        </div>
      ) : (
        <ul className="notifications-list" aria-label="Примеры уведомлений">
          {EXAMPLE_NOTIFICATIONS.map((notification) => (
            <li key={notification.id}>
              <button
                type="button"
                className="notification-card card-surface"
                onClick={() => setSelected(notification)}
              >
                <span className="notification-icon">
                  <notification.Icon aria-hidden="true" />
                </span>
                <span className="notification-copy">
                  <span className="notification-title-row">
                    <strong>{notification.title}</strong>
                    <StatusBadge tone="neutral">Пример</StatusBadge>
                  </span>
                  <span>{notification.preview}</span>
                  <small>{notification.when}</small>
                </span>
                <ChevronRight className="notification-chevron" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}
      {selected && <NotificationSheet notification={selected} onClose={() => setSelected(null)} />}
    </section>
  );
}
