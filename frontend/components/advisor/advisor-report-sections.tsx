"use client";

import { BarChart3, CircleHelp, FileText, ShieldCheck, Sparkles, Wallet } from "lucide-react";
import { StatusBadge } from "@/components/common";
import type { AdvisorReport } from "@/lib/types";
import { Disclaimers, EvidenceFacts, PRIORITY_LABELS, PRIORITY_TONE } from "./advisor-common";

function Section({
  title,
  Icon,
  children,
}: {
  title: string;
  Icon: typeof BarChart3;
  children: React.ReactNode;
}) {
  return (
    <details className="advisor-report-section card-surface" open>
      <summary>
        <span>
          <Icon aria-hidden="true" /> {title}
        </span>
      </summary>
      {children}
    </details>
  );
}

function TextList({ items, empty }: { items: string[]; empty: string }) {
  if (!items.length) return <p className="advisor-muted">{empty}</p>;
  return (
    <ul className="advisor-list">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

export function ReportSections({ report }: { report: AdvisorReport }) {
  const data = report.report;
  const factIds = report.facts.map((fact) => fact.id);
  const factsTitle = factIds.length > 1 ? `Факты ${factIds[0]}–${factIds.at(-1)}` : "Факты";
  return (
    <div className="advisor-report-sections">
      <section className="advisor-report-summary card-surface">
        <span className="advisor-kicker">
          <FileText aria-hidden="true" /> Краткий обзор
        </span>
        <p>{data.summary}</p>
      </section>
      <Section title="Наблюдения" Icon={BarChart3}>
        {data.insights.length === 0 && <p className="advisor-muted">Наблюдений нет.</p>}
        <div className="advisor-report-items">
          {data.insights.map((insight, index) => (
            <article key={`${index}-${insight.title}`}>
              <span className="advisor-report-icon">
                <CircleHelp aria-hidden="true" />
              </span>
              <div>
                <span className="advisor-kicker">{insight.area}</span>
                <h3>{insight.title}</h3>
                <p>{insight.explanation}</p>
                <EvidenceFacts facts={report.facts} ids={insight.evidence} />
              </div>
            </article>
          ))}
        </div>
      </Section>
      <Section title="Рекомендации" Icon={Sparkles}>
        {data.recommendations.length === 0 && <p className="advisor-muted">Рекомендаций нет.</p>}
        <div className="advisor-report-items">
          {data.recommendations.map((recommendation, index) => (
            <article key={`${index}-${recommendation.title}`} data-testid="advisor-recommendation">
              <span className="advisor-report-icon">
                <Wallet aria-hidden="true" />
              </span>
              <div>
                <div className="advisor-report-badges">
                  <StatusBadge tone={PRIORITY_TONE[recommendation.priority]}>
                    Приоритет: {PRIORITY_LABELS[recommendation.priority]}
                  </StatusBadge>
                  {recommendation.involves_investment && (
                    <StatusBadge tone="info">Касается инвестиций</StatusBadge>
                  )}
                </div>
                <h3>{recommendation.title}</h3>
                <p>
                  <strong>Действие:</strong> {recommendation.action}
                </p>
                <p>{recommendation.reasoning}</p>
                <EvidenceFacts facts={report.facts} ids={recommendation.evidence} />
                {recommendation.assumptions.length > 0 && (
                  <p className="advisor-muted">
                    Допущения: {recommendation.assumptions.join("; ")}
                  </p>
                )}
              </div>
            </article>
          ))}
        </div>
      </Section>
      <Section title="Риски" Icon={ShieldCheck}>
        {data.risks.length === 0 && (
          <p className="advisor-muted">Существенных рисков не найдено.</p>
        )}
        <div className="advisor-report-items">
          {data.risks.map((risk, index) => (
            <article key={`${index}-${risk.title}`}>
              <span className="advisor-report-icon">
                <ShieldCheck aria-hidden="true" />
              </span>
              <div>
                <StatusBadge tone={PRIORITY_TONE[risk.severity]}>
                  Серьёзность: {PRIORITY_LABELS[risk.severity]}
                </StatusBadge>
                <h3>{risk.title}</h3>
                <p>{risk.explanation}</p>
                <EvidenceFacts facts={report.facts} ids={risk.evidence} />
              </div>
            </article>
          ))}
        </div>
      </Section>
      <Section title="Допущения" Icon={CircleHelp}>
        <TextList items={data.assumptions} empty="Дополнительных допущений нет." />
      </Section>
      <Section title="Каких данных не хватает" Icon={CircleHelp}>
        <TextList
          items={data.data_gaps}
          empty="Для этого отчёта дополнительных данных не требуется."
        />
      </Section>
      <Section title={factsTitle} Icon={BarChart3}>
        <EvidenceFacts facts={report.facts} ids={factIds} />
      </Section>
      <Disclaimers
        items={[
          ...report.disclaimers,
          "Отчёт не является обещанием доходности, инвестиционной рекомендацией или гарантией одобрения кредита.",
        ]}
      />
    </div>
  );
}
