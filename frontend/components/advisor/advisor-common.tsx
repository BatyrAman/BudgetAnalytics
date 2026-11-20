"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FileText, MessageSquareText } from "lucide-react";
import { ApiError, toUserMessage } from "@/lib/api/errors";
import type { AdvisorMeta, Fact } from "@/lib/types";

export const ADVISOR_RATE_LIMIT_MESSAGE = "Лимит запросов к советнику: 30 в час. Попробуйте позже";

export const FALLBACK_TEXT: Record<NonNullable<AdvisorMeta["fallback_reason"]>, string> = {
  disabled: "AI отключён, ответ подготовлен по правилам",
  limit_reached: "Дневной лимит AI исчерпан — ответ подготовлен по правилам",
  provider_error: "AI временно недоступен — ответ подготовлен по правилам",
  invalid_output: "Ответ AI не прошёл проверку — показан ответ по правилам",
};

export const PRIORITY_LABELS = { high: "Высокий", medium: "Средний", low: "Низкий" } as const;
export const PRIORITY_TONE = { high: "negative", medium: "warning", low: "neutral" } as const;

/** Russian message for an advisor request failure (429 has a dedicated text). */
export function advisorErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 429) return ADVISOR_RATE_LIMIT_MESSAGE;
  return toUserMessage(error);
}

/** `as_of` is an ISO date (YYYY-MM-DD) → DD.MM.YYYY without time-zone shifts. */
export function formatAsOf(value: string): string {
  const [year, month, day] = value.slice(0, 10).split("-");
  return year && month && day ? `${day}.${month}.${year}` : value;
}

export function AdvisorTabs() {
  const path = usePathname();
  return (
    <nav className="advisor-tabs" aria-label="Разделы советника">
      <Link href="/advisor" aria-current={path === "/advisor" ? "page" : undefined}>
        <MessageSquareText aria-hidden="true" /> Вопрос
      </Link>
      <Link href="/advisor/report" aria-current={path === "/advisor/report" ? "page" : undefined}>
        <FileText aria-hidden="true" /> Финансовый отчёт
      </Link>
    </nav>
  );
}

/** Facts referenced by `ids` (evidence), in the order the API returned them. */
export function EvidenceFacts({ facts, ids }: { facts: Fact[]; ids: string[] }) {
  const wanted = new Set(ids);
  const evidence = facts.filter((fact) => wanted.has(fact.id));
  if (!evidence.length)
    return <p className="advisor-muted">Нет фактов, указанных для этого ответа.</p>;
  return (
    <ul className="advisor-fact-list">
      {evidence.map((fact) => (
        <li key={fact.id} data-testid="advisor-fact">
          <span className="advisor-fact-id">{fact.id}</span>
          <div>
            <strong>{fact.label}</strong>
            <span>
              {fact.value} {fact.unit}
              {fact.period ? ` · ${fact.period}` : ""}
            </span>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function Disclaimers({ items }: { items: string[] }) {
  if (!items.length) return null;
  return (
    <ul className="advisor-disclaimers">
      {items.map((disclaimer) => (
        <li key={disclaimer}>{disclaimer}</li>
      ))}
    </ul>
  );
}
