"""Deterministic, rule-based advice built ONLY from the fact sheet.

Used when the LLM is disabled, over its limits, failing, or produced output
that did not pass the guard. Every number is copied verbatim from a fact and
every statement cites it, so the result passes the same guard as LLM output.
Thresholds are conventional rules of thumb, stated as assumptions.
"""

from decimal import Decimal

from app.schemas.advisor import AdvisorAnswer, AdvisorReport, Insight, Recommendation, Risk
from app.services.ai.facts import Fact, FactSheet

LOW_SAVINGS_RATE = Decimal("10")
SAFETY_CUSHION_MONTHS = Decimal("3")


def _last_complete(sheet: FactSheet, topic: str, prefix: str) -> Fact | None:
    """The fact for the most recent COMPLETE month (current month is flagged)."""

    for fact in sheet.facts:
        if (
            fact.topic == topic
            and fact.label.startswith(prefix)
            and "не закончился" not in fact.label
        ):
            return fact
    return None


def build_report(sheet: FactSheet) -> AdvisorReport:
    insights: list[Insight] = []
    risks: list[Risk] = []
    recs: list[Recommendation] = []

    income = _last_complete(sheet, "income", "Доход за месяц")
    expenses = _last_complete(sheet, "expenses", "Расходы за месяц")
    flow = _last_complete(sheet, "cash_flow", "Чистый денежный поток")
    rate = _last_complete(sheet, "savings", "Норма сбережений")

    if income and expenses and flow:
        summary = (
            f"За {income.period}: доход {income.value} {income.unit}, расходы {expenses.value} "
            f"{expenses.unit}, чистый денежный поток {flow.value} {flow.unit}."
        )
        insights.append(
            Insight(
                area="cash_flow",
                title="Денежный поток последнего полного месяца",
                explanation=summary,
                evidence=[income.id, expenses.id, flow.id],
            )
        )
        if Decimal(flow.value) < 0:
            risks.append(
                Risk(
                    title="Расходы превысили доходы",
                    explanation=(
                        f"Чистый денежный поток за {flow.period} "
                        f"отрицательный: {flow.value} {flow.unit}."
                    ),
                    severity="high",
                    evidence=[flow.id],
                )
            )
    else:
        summary = "Недостаточно данных для обзора."

    if rate is not None:
        insights.append(
            Insight(
                area="savings",
                title="Норма сбережений",
                explanation=f"Норма сбережений за {rate.period}: {rate.value} %.",
                evidence=[rate.id],
            )
        )
        if Decimal(rate.value) < LOW_SAVINGS_RATE:
            recs.append(
                Recommendation(
                    title="Увеличить долю сбережений",
                    action=(
                        "Пересмотрите крупнейшие категории расходов "
                        "и запланируйте фиксированную сумму "
                        "на сбережения сразу после получения дохода."
                    ),
                    reasoning=f"Норма сбережений за {rate.period} составила {rate.value} %.",
                    evidence=[rate.id],
                    assumptions=[
                        "Ориентир «не менее 10 % дохода» — общее правило, а не требование."
                    ],
                    priority="high",
                    involves_investment=False,
                )
            )

    change = sheet.find("expenses", "Изменение расходов")
    if change is not None:
        direction = "выросли" if Decimal(change.value) > 0 else "снизились"
        insights.append(
            Insight(
                area="expenses",
                title="Динамика расходов",
                explanation=(
                    f"Расходы {direction} на {change.value.lstrip('-')} % к предыдущему месяцу."
                ),
                evidence=[change.id],
            )
        )

    top = next((f for f in sheet.facts if f.label.startswith("Расходы по категории")), None)
    if top is not None:
        insights.append(
            Insight(
                area="expenses",
                title="Крупнейшая категория расходов",
                explanation=f"{top.label}: {top.value} {top.unit} за {top.period}.",
                evidence=[top.id],
            )
        )
        recs.append(
            Recommendation(
                title="Проверить крупнейшую категорию",
                action=(
                    "Разберите операции крупнейшей категории "
                    "и решите, какие из них можно сократить."
                ),
                reasoning=f"{top.label} — {top.value} {top.unit}.",
                evidence=[top.id],
                assumptions=[],
                priority="medium",
                involves_investment=False,
            )
        )

    for fact in sheet.facts:
        if fact.topic == "budget" and fact.label.endswith(": превышен") and fact.value == "да":
            budget = fact.label.removesuffix(": превышен")
            risks.append(
                Risk(
                    title="Бюджет превышен",
                    explanation=f"{budget} превышен в текущем месяце.",
                    severity="medium",
                    evidence=[fact.id],
                )
            )
            recs.append(
                Recommendation(
                    title="Скорректировать бюджет или траты",
                    action=(
                        f"Сократите траты по {budget} до конца месяца "
                        "или пересмотрите лимит, если он нереалистичен."
                    ),
                    reasoning=f"{budget} уже превышен.",
                    evidence=[fact.id],
                    assumptions=[],
                    priority="medium",
                    involves_investment=False,
                )
            )

    cushion = sheet.find("balance", "На сколько месяцев")
    if cushion is not None and Decimal(cushion.value) < SAFETY_CUSHION_MONTHS:
        risks.append(
            Risk(
                title="Небольшая финансовая подушка",
                explanation=f"Баланса хватит примерно на {cushion.value} мес. средних расходов.",
                severity="medium",
                evidence=[cushion.id],
            )
        )
        recs.append(
            Recommendation(
                title="Сформировать резерв",
                action=(
                    "Откладывайте часть дохода на отдельный счёт "
                    "до резерва в несколько месяцев расходов."
                ),
                reasoning=f"Текущего баланса хватит примерно на {cushion.value} мес.",
                evidence=[cushion.id],
                assumptions=[
                    "Резерв на 3–6 месяцев расходов — распространённый ориентир, а не правило."
                ],
                priority="high",
                involves_investment=False,
            )
        )

    for fact in sheet.facts:
        if fact.topic == "goal" and fact.label.endswith(
            "нужно откладывать в месяц (равными частями, без процентов)"
        ):
            goal = fact.label.split(":")[0]
            insights.append(
                Insight(
                    area="goal",
                    title="Темп накоплений для цели",
                    explanation=(
                        f"{goal}: чтобы успеть к сроку, нужно "
                        f"откладывать {fact.value} {fact.unit} в месяц."
                    ),
                    evidence=[fact.id],
                )
            )

    return AdvisorReport(
        summary=summary,
        insights=insights[:8],
        recommendations=recs[:6],
        risks=risks[:5],
        assumptions=[
            "Рекомендации основаны на правилах и не учитывают вашу полную финансовую ситуацию."
        ],
        data_gaps=sheet.data_gaps[:10],
    )


def build_answer(sheet: FactSheet) -> AdvisorAnswer:
    report = build_report(sheet)
    return AdvisorAnswer(
        answer="AI-помощник сейчас недоступен, поэтому я не могу ответить на вопрос свободно. "
        "Вот проверенная сводка ваших данных: " + report.summary,
        evidence=[e for i in report.insights[:1] for e in i.evidence],
        assumptions=[],
        involves_investment=False,
        needs_more_data=False,
        follow_up_question=None,
    )
