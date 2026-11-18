from datetime import date
from decimal import Decimal

import pytest

from app.core.config import Settings
from app.integrations.llm import TokenUsage
from app.schemas.advisor import AdvisorAnswer, AdvisorReport, Insight, Recommendation
from app.services.ai import fallback, guard
from app.services.ai.facts import Fact, FactSheet
from app.services.ai.prompts import redact_question
from app.services.ai.usage import cost_usd


def sheet() -> FactSheet:
    s = FactSheet("KZT", "Asia/Almaty", date(2025, 4, 10))
    s.facts = [
        Fact("F1", "income", "Доход за месяц", "600000.00", "KZT", "2025-03"),
        Fact(
            "F2",
            "expenses",
            "Расходы за месяц (за вычетом возвратов)",
            "255000.00",
            "KZT",
            "2025-03",
        ),
        Fact("F3", "cash_flow", "Чистый денежный поток за месяц", "345000.00", "KZT", "2025-03"),
        Fact("F4", "savings", "Норма сбережений за месяц", "57.50", "%", "2025-03"),
        Fact(
            "F5",
            "expenses",
            "Изменение расходов последнего полного месяца к предыдущему",
            "-15.00",
            "%",
            "2025-03",
        ),
        Fact("F6", "expenses", "Расходы по категории «[CAT-1]»", "200000.00", "KZT", "2025-03"),
        Fact("F7", "deposit", "Вклад 1: дата окончания", "2026-01-01", "date"),
        Fact("F8", "budget", "Бюджет [BUDGET-1] (Продукты): превышен", "да", "flag", "2025-04"),
        Fact(
            "F9", "balance", "На сколько месяцев средних расходов хватит баланса", "1.67", "months"
        ),
    ]
    s.pseudonyms = {"[CAT-1]": "Долг Ивану", "[BUDGET-1]": "Еда"}
    return s


def report(text: str, evidence: list[str] | None = None) -> AdvisorReport:
    return AdvisorReport(
        summary=text,
        insights=[
            Insight(
                area="savings", title="Сбережения", explanation="ok", evidence=evidence or ["F4"]
            )
        ],
        recommendations=[],
        risks=[],
        assumptions=[],
        data_gaps=[],
    )


class TestNumberGrounding:
    @pytest.mark.parametrize(
        "text",
        [
            "Доход составил 600000.00 KZT.",
            "Доход составил 600 000 ₸, расходы 255 000,00 ₸.",  # spaces and decimal comma
            "Норма сбережений 57,5 %, расходы снизились на 15 %.",
            "Чистый поток 345 000 тенге.",
            "Вклад закончится 2026-01-01, через 3 месяца.",  # date parts, small integer
            "Хватит примерно на 1,67 месяца.",
            "Согласно F4 и F9, подушка небольшая.",  # fact ids are not numbers
            "Категория [CAT-1] самая крупная.",
        ],
    )
    def test_grounded_text_passes(self, text: str) -> None:
        guard.check_report(report(text), sheet())

    @pytest.mark.parametrize(
        "text",
        [
            "Если откладывать 50 000 ₸ в месяц...",  # invented amount
            "Ставка по вкладу 18,5 % годовых.",  # invented rate
            "За год вы сэкономите 3 060 000 ₸.",  # model-made arithmetic (255 000 × 12)
            "Разница составила 345001 KZT.",
            "Средний доход 13 месяцев",  # 13 is not a small count
            "Доходность 12 % годовых.",  # small number, but a RATE -> must be a fact
            "Комиссия всего 5 ₸.",  # small number, but an AMOUNT
            "Это стоит $7.",
            "Инфляция около 8 процентов.",
        ],
    )
    def test_invented_numbers_are_rejected(self, text: str) -> None:
        with pytest.raises(guard.GuardViolation, match="ungrounded"):
            guard.check_report(report(text), sheet())

    def test_unknown_or_missing_evidence(self) -> None:
        with pytest.raises(guard.GuardViolation, match="unknown fact ids"):
            guard.check_report(report("ok", ["F99"]), sheet())
        bad = report("ok")
        bad.insights[0].evidence = []
        with pytest.raises(guard.GuardViolation, match="without evidence"):
            guard.check_report(bad, sheet())

    def test_numbers_in_recommendation_fields_are_checked_too(self) -> None:
        r = report("ok")
        r.recommendations.append(
            Recommendation(
                title="Копить",
                action="Откладывайте 77 777 ₸",
                reasoning="F4",
                evidence=["F4"],
                assumptions=[],
                priority="high",
                involves_investment=False,
            )
        )
        with pytest.raises(guard.GuardViolation):
            guard.check_report(r, sheet())

    def test_answer_check(self) -> None:
        ok = AdvisorAnswer(
            answer="Норма сбережений 57,50 %.",
            evidence=["F4"],
            assumptions=[],
            involves_investment=False,
            needs_more_data=False,
            follow_up_question=None,
        )
        guard.check_answer(ok, sheet())
        bad = ok.model_copy(update={"answer": "Ожидаемая доходность акций 12 % годовых."})
        with pytest.raises(guard.GuardViolation):
            guard.check_answer(bad, sheet())


class TestFallback:
    def test_rule_based_report_is_grounded_and_cites_facts(self) -> None:
        s = sheet()
        result = fallback.build_report(s)
        guard.check_report(result, s)  # passes the same guard as LLM output
        assert "600000.00" in result.summary and "345000.00" in result.summary
        titles = {r.title for r in result.risks}
        assert {"Бюджет превышен", "Небольшая финансовая подушка"} <= titles
        assert not any(r.involves_investment for r in result.recommendations)

    def test_empty_sheet(self) -> None:
        empty = FactSheet("KZT", "Asia/Almaty", date(2025, 1, 1), data_gaps=["Нет данных"])
        result = fallback.build_report(empty)
        assert result.summary == "Недостаточно данных для обзора." and result.data_gaps == [
            "Нет данных"
        ]
        guard.check_answer(fallback.build_answer(empty), empty)


class TestRedaction:
    @pytest.mark.parametrize(
        ("question", "leaked"),
        [
            ("мой email ivan.petrov@mail.kz что делать", "ivan.petrov@mail.kz"),
            ("карта 4400 4300 1234 5678 списали", "4400 4300 1234 5678"),
            ("ИИН 900101300123 налог", "900101300123"),
            ("позвоните +7 701 123 45 67", "701 123 45 67"),
        ],
    )
    def test_identifiers_are_removed(self, question: str, leaked: str) -> None:
        assert leaked not in redact_question(question)

    def test_ordinary_amounts_are_kept(self) -> None:
        assert "50 000" in redact_question("Можно ли откладывать 50 000 в месяц?")


class TestCost:
    def _settings(self, **values: object) -> Settings:
        return Settings(
            _env_file=None,
            DATABASE_URL="postgresql+asyncpg://u:p@h/db",
            SECRET_KEY="x" * 40,
            **values,
        )  # type: ignore[arg-type]

    def test_cost_from_configured_prices(self) -> None:
        s = self._settings(
            AI_INPUT_PRICE_PER_1M_TOKENS_USD="0.15", AI_OUTPUT_PRICE_PER_1M_TOKENS_USD="0.60"
        )
        # 1 200 × 0.15 / 1e6 + 800 × 0.60 / 1e6 = 0.00018 + 0.00048 = 0.00066
        assert cost_usd(TokenUsage(1200, 800), s) == Decimal("0.000660")

    def test_unknown_without_prices(self) -> None:
        assert cost_usd(TokenUsage(1, 1), self._settings()) is None
