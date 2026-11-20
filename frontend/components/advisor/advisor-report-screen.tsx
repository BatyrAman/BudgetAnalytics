"use client";

import Link from "next/link";
import { useState } from "react";
import { FileText, ShieldCheck, Sparkles } from "lucide-react";
import { Skeleton } from "@/components/common";
import { getAdvisorReport } from "@/lib/api/client";
import { useDefaultCurrency } from "@/lib/api/hooks";
import type { AdvisorReport } from "@/lib/types";
import { AdvisorTabs, FALLBACK_TEXT, advisorErrorMessage, formatAsOf } from "./advisor-common";
import { ReportSections } from "./advisor-report-sections";

export function AdvisorReportScreen() {
  const currency = useDefaultCurrency();
  const [report, setReport] = useState<AdvisorReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function generateReport() {
    setLoading(true);
    setError("");
    try {
      setReport(await getAdvisorReport(currency));
    } catch (requestError) {
      setError(advisorErrorMessage(requestError));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="advisor-page advisor-report-page">
      <AdvisorTabs />
      <div className="advisor-report-heading">
        <div>
          <h2>Финансовый отчёт</h2>
          <p>Сводка по вашим операциям, счетам, бюджетам и целям</p>
        </div>
        <button
          type="button"
          className="button primary"
          onClick={() => void generateReport()}
          disabled={loading}
        >
          <Sparkles aria-hidden="true" /> {loading ? "Формирую…" : "Сформировать отчёт"}
        </button>
      </div>
      <p className="advisor-report-notice">
        Отчёт не сохраняется; повторное формирование расходует лимит
      </p>
      {error && (
        <p className="advisor-error" role="alert">
          {error}
        </p>
      )}
      {loading && (
        <div className="advisor-loading" role="status" aria-live="polite">
          <span className="advisor-source">
            <Sparkles aria-hidden="true" /> Анализирую ваши данные…
          </span>
          <Skeleton />
          <Skeleton className="short" />
        </div>
      )}
      {!report && !loading && (
        <div className="advisor-report-empty card-surface">
          <span className="advisor-report-icon">
            <FileText aria-hidden="true" />
          </span>
          <h3>Отчёта пока нет</h3>
          <p>Сформируйте отчёт, чтобы увидеть наблюдения, рекомендации и риски.</p>
        </div>
      )}
      {report && !loading && (
        <>
          <div className="advisor-answer-head">
            <span className="advisor-source">
              {report.generated_by === "llm" ? (
                <Sparkles aria-hidden="true" />
              ) : (
                <ShieldCheck aria-hidden="true" />
              )}
              {report.generated_by === "llm" ? "AI" : "Отчёт по правилам"}
            </span>
            <span className="advisor-as-of">Данные на {formatAsOf(report.as_of)}</span>
          </div>
          {report.generated_by === "rules" && report.fallback_reason && (
            <p className="advisor-fallback" role="status">
              {FALLBACK_TEXT[report.fallback_reason]}
            </p>
          )}
          <ReportSections report={report} />
        </>
      )}
      <Link href="/advisor" className="advisor-back-link">
        ← Вернуться к вопросу
      </Link>
    </div>
  );
}
