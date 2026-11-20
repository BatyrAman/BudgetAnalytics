import type { AdvisorAnswer, AdvisorReport, Fact } from "@/lib/types";

/** Test-only builders (imported only by *.test.tsx). */
export const FACTS: Fact[] = [
  {
    id: "F1",
    topic: "spending",
    label: "Расходы за месяц",
    value: "120000.00",
    unit: "KZT",
    period: "2025-01",
  },
  {
    id: "F2",
    topic: "income",
    label: "Доход за месяц",
    value: "300000.00",
    unit: "KZT",
    period: null,
  },
  {
    id: "F3",
    topic: "savings",
    label: "Подушка безопасности",
    value: "2.5",
    unit: "мес.",
    period: null,
  },
];

export function makeAnswer(overrides: Partial<AdvisorAnswer> = {}): AdvisorAnswer {
  return {
    generated_by: "llm",
    fallback_reason: null,
    currency_code: "KZT",
    as_of: "2025-01-31",
    facts: FACTS,
    disclaimers: ["Это не индивидуальная инвестиционная рекомендация."],
    answer: {
      answer: "Больше всего уходит на продукты.",
      evidence: ["F1", "F3"],
      assumptions: ["Учтены только операции за месяц"],
      involves_investment: false,
      needs_more_data: false,
      follow_up_question: null,
    },
    ...overrides,
  };
}

export function makeReport(overrides: Partial<AdvisorReport> = {}): AdvisorReport {
  return {
    generated_by: "llm",
    fallback_reason: null,
    currency_code: "KZT",
    as_of: "2025-01-31",
    facts: FACTS,
    disclaimers: ["Расчёты носят информационный характер."],
    report: {
      summary: "Расходы стабильны.",
      insights: [
        {
          area: "Расходы",
          title: "Продукты лидируют",
          explanation: "Продукты — крупнейшая статья.",
          evidence: ["F1"],
        },
      ],
      recommendations: [
        {
          title: "Сократить кафе",
          action: "Установить бюджет",
          reasoning: "Кафе растут.",
          evidence: ["F1"],
          assumptions: [],
          priority: "high",
          involves_investment: false,
        },
        {
          title: "Пополнять резерв",
          action: "Откладывать часть дохода",
          reasoning: "Подушка ниже 3 мес.",
          evidence: ["F3"],
          assumptions: [],
          priority: "medium",
          involves_investment: false,
        },
        {
          title: "Изучить депозиты",
          action: "Сравнить условия",
          reasoning: "Свободные средства.",
          evidence: ["F2"],
          assumptions: [],
          priority: "low",
          involves_investment: true,
        },
      ],
      risks: [
        {
          title: "Мало резерва",
          explanation: "Подушка меньше 3 месяцев.",
          severity: "high",
          evidence: ["F3"],
        },
      ],
      assumptions: ["Доход стабилен"],
      data_gaps: ["Нет данных о кредитах"],
    },
    ...overrides,
  };
}
