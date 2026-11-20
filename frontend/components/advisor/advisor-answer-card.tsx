"use client";

import { ShieldCheck, Sparkles } from "lucide-react";
import type { AdvisorAnswer } from "@/lib/types";
import { Disclaimers, EvidenceFacts, FALLBACK_TEXT, formatAsOf } from "./advisor-common";

export function AnswerCard({
  answer,
  onFollowUp,
  followUpDisabled = false,
}: {
  answer: AdvisorAnswer;
  onFollowUp?: (question: string) => void;
  followUpDisabled?: boolean;
}) {
  const isLlm = answer.generated_by === "llm";
  const followUp = answer.answer.follow_up_question;
  return (
    <article className="advisor-answer card-surface">
      <div className="advisor-answer-head">
        <span className="advisor-source">
          {isLlm ? <Sparkles aria-hidden="true" /> : <ShieldCheck aria-hidden="true" />}
          {isLlm ? "AI" : "Ответ по правилам"}
        </span>
        <span className="advisor-as-of">Данные на {formatAsOf(answer.as_of)}</span>
      </div>
      {!isLlm && answer.fallback_reason && (
        <p className="advisor-fallback" role="status">
          {FALLBACK_TEXT[answer.fallback_reason]}
        </p>
      )}
      <p className="advisor-answer-text">{answer.answer.answer}</p>
      {answer.answer.involves_investment && (
        <p className="advisor-note">Ответ касается инвестиций. Доходность не гарантируется.</p>
      )}
      <details className="advisor-disclosure">
        <summary>На чём основан ответ</summary>
        <EvidenceFacts facts={answer.facts} ids={answer.answer.evidence} />
      </details>
      {answer.answer.assumptions.length > 0 && (
        <div className="advisor-subsection">
          <h4>Допущения</h4>
          <ul>
            {answer.answer.assumptions.map((assumption) => (
              <li key={assumption}>{assumption}</li>
            ))}
          </ul>
        </div>
      )}
      {answer.answer.needs_more_data && (
        <p className="advisor-data-hint">Добавьте операции или счета, чтобы ответ был точнее</p>
      )}
      {followUp && onFollowUp && (
        <button
          type="button"
          className="advisor-follow-up"
          disabled={followUpDisabled}
          onClick={() => onFollowUp(followUp)}
        >
          {followUp}
        </button>
      )}
      <Disclaimers items={answer.disclaimers} />
    </article>
  );
}
