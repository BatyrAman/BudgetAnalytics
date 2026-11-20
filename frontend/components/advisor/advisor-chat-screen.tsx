"use client";

import { useState } from "react";
import { BarChart3, Send, Sparkles } from "lucide-react";
import { Skeleton } from "@/components/common";
import { askAdvisor } from "@/lib/api/client";
import { useDefaultCurrency } from "@/lib/api/hooks";
import type { AdvisorAnswer } from "@/lib/types";
import { AnswerCard } from "./advisor-answer-card";
import { AdvisorTabs, EvidenceFacts, advisorErrorMessage } from "./advisor-common";

export const QUESTION_MIN = 3;
export const QUESTION_MAX = 500;
const VALIDATION_MESSAGE = "Вопрос должен быть от 3 до 500 символов";

const PROMPTS = [
  "Куда уходит больше всего денег?",
  "Хватит ли подушки безопасности?",
  "Как сократить расходы на кафе?",
];

/** One question/answer pair. Kept only in React state for this page visit. */
type AdvisorTurn = { id: number; question: string; answer: AdvisorAnswer };

export function AdvisorChatScreen() {
  const currency = useDefaultCurrency();
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<AdvisorTurn[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const latest = turns.at(-1)?.answer;

  async function submitQuestion(value: string) {
    const trimmed = value.trim();
    if (trimmed.length < QUESTION_MIN || trimmed.length > QUESTION_MAX) {
      setError(VALIDATION_MESSAGE);
      return;
    }
    setError("");
    setLoading(true);
    try {
      // Every question is independent: only the question text is sent, never history.
      const answer = await askAdvisor(trimmed, currency);
      setTurns((current) => [...current, { id: current.length, question: trimmed, answer }]);
      setQuestion("");
    } catch (requestError) {
      setError(advisorErrorMessage(requestError));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="advisor-page">
      <AdvisorTabs />
      <div className="advisor-layout">
        <section className="advisor-conversation" aria-label="Диалог с советником">
          <div className="advisor-intro">
            <span className="advisor-intro-icon">
              <Sparkles aria-hidden="true" />
            </span>
            <div>
              <h2>Финансовый советник</h2>
              <p>Задайте вопрос о своих данных. Каждый запрос рассматривается отдельно.</p>
            </div>
          </div>
          {turns.length === 0 && (
            <div className="advisor-suggestions">
              <p>Можно начать с одного из вопросов</p>
              <div>
                {PROMPTS.map((prompt) => (
                  <button
                    type="button"
                    key={prompt}
                    onClick={() => void submitQuestion(prompt)}
                    disabled={loading}
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          )}
          {turns.map((turn) => (
            <div className="advisor-turn" key={turn.id}>
              <div className="advisor-question">
                <span>Вы</span>
                <p>{turn.question}</p>
              </div>
              <AnswerCard
                answer={turn.answer}
                followUpDisabled={loading}
                onFollowUp={(followUp) => void submitQuestion(followUp)}
              />
            </div>
          ))}
          {loading && (
            <div className="advisor-loading" role="status" aria-live="polite">
              <span className="advisor-source">
                <Sparkles aria-hidden="true" /> Анализирую ваши данные…
              </span>
              <Skeleton />
              <Skeleton className="short" />
            </div>
          )}
          {error && (
            <p className="advisor-error" role="alert">
              {error}
            </p>
          )}
          <p className="advisor-history-note">
            История не сохраняется: каждый вопрос обрабатывается отдельно
          </p>
          <form
            className="advisor-composer"
            noValidate
            onSubmit={(event) => {
              event.preventDefault();
              void submitQuestion(question);
            }}
          >
            <label className="sr-only" htmlFor="advisor-question">
              Ваш вопрос
            </label>
            <textarea
              id="advisor-question"
              aria-describedby="advisor-warning advisor-counter"
              aria-invalid={error === VALIDATION_MESSAGE}
              value={question}
              maxLength={QUESTION_MAX}
              rows={2}
              placeholder="Напишите вопрос о своих финансах…"
              onChange={(event) => {
                setQuestion(event.target.value);
                if (error) setError("");
              }}
            />
            <div className="advisor-composer-foot">
              <span id="advisor-warning">Не указывайте номера карт, ИИН и пароли</span>
              <span
                id="advisor-counter"
                className={question.length >= QUESTION_MAX ? "advisor-count full" : "advisor-count"}
              >
                {question.length} / {QUESTION_MAX}
              </span>
              <button
                type="submit"
                className="button primary"
                disabled={loading}
                aria-label="Отправить вопрос"
              >
                <Send aria-hidden="true" /> Отправить
              </button>
            </div>
          </form>
        </section>
        <aside className="advisor-facts-panel card-surface" aria-label="Факты последнего ответа">
          <h3>
            <BarChart3 aria-hidden="true" /> Факты последнего ответа
          </h3>
          {latest ? (
            <EvidenceFacts facts={latest.facts} ids={latest.answer.evidence} />
          ) : (
            <p>После ответа здесь появятся факты, на которые он опирается.</p>
          )}
        </aside>
      </div>
    </div>
  );
}
