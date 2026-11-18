"""Verified facts for the AI advisor.

Every number here is produced by deterministic services (SQL aggregates +
``app.services.finance``). The LLM receives ONLY this fact sheet: it may
quote these values and must cite their ids; it never computes new numbers.

PRIVACY
* No user name, e-mail, ids, account names/numbers or transaction descriptions.
* User-entered names (private categories, budget titles, goal names) are
  replaced by tokens ``[CAT-1]``, ``[BUDGET-1]``, ``[GOAL-1]``; the real names
  are kept server-side (``pseudonyms``) and substituted back into the answer.
* System category names and bank names are reference data and sent as is.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.budget import Budget
from app.models.category import Category
from app.models.deposit import Deposit
from app.models.enums import Capitalization
from app.models.goal import FinancialGoal
from app.models.user import User
from app.services.accounts import AccountService
from app.services.deposit_service import PERIODS_PER_YEAR
from app.services.deposits import maturity_of
from app.services.finance import (
    CurrencySpec,
    average,
    effective_annual_rate,
    emergency_fund_months,
    month_period,
    percent_change,
    share_percent,
)
from app.services.finance.indicators import months_until, required_monthly_saving
from app.services.finance.money import calc_context, quantize_money
from app.services.financial_summary import FinancialSummaryService

HISTORY_MONTHS = 6
TOP_CATEGORIES = 5

_CAPITALIZATION_RU = {
    Capitalization.NONE: "без капитализации",
    Capitalization.MONTHLY: "ежемесячная капитализация",
    Capitalization.QUARTERLY: "ежеквартальная капитализация",
    Capitalization.ANNUALLY: "ежегодная капитализация",
}


@dataclass(frozen=True)
class Fact:
    id: str
    topic: str
    label: str
    value: str
    unit: str
    period: str | None = None

    def as_prompt(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "topic": self.topic,
            "label": self.label,
            "value": self.value,
            "unit": self.unit,
        }
        if self.period:
            data["period"] = self.period
        return data


@dataclass
class FactSheet:
    currency_code: str
    timezone: str
    as_of: date
    facts: list[Fact] = field(default_factory=list)
    data_gaps: list[str] = field(default_factory=list)
    pseudonyms: dict[str, str] = field(default_factory=dict)  # token -> real name

    def by_id(self) -> dict[str, Fact]:
        return {f.id: f for f in self.facts}

    def find(self, topic: str, label_prefix: str) -> Fact | None:
        for fact in self.facts:
            if fact.topic == topic and fact.label.startswith(label_prefix):
                return fact
        return None

    def to_prompt(self) -> dict[str, Any]:
        return {
            "currency": self.currency_code,
            "timezone": self.timezone,
            "as_of": self.as_of.isoformat(),
            "facts": [f.as_prompt() for f in self.facts],
            "data_gaps": self.data_gaps,
        }


class _Builder:
    def __init__(self, sheet: FactSheet) -> None:
        self.sheet = sheet
        self._counters: dict[str, int] = {}

    def add(
        self, topic: str, label: str, value: object, unit: str, period: str | None = None
    ) -> Fact | None:
        if value is None:
            return None
        fact = Fact(f"F{len(self.sheet.facts) + 1}", topic, label, str(value), unit, period)
        self.sheet.facts.append(fact)
        return fact

    def token(self, kind: str, real_name: str) -> str:
        for token, name in self.sheet.pseudonyms.items():
            if name == real_name and token.startswith(f"[{kind}-"):
                return token
        self._counters[kind] = self._counters.get(kind, 0) + 1
        token = f"[{kind}-{self._counters[kind]}]"
        self.sheet.pseudonyms[token] = real_name
        return token


def _shift(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + month - 1 + delta
    return index // 12, index % 12 + 1


class FactSheetBuilder:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.summary = FinancialSummaryService(db)

    async def build(
        self, user: User, currency: CurrencySpec, tz: ZoneInfo, today: date
    ) -> FactSheet:
        sheet = FactSheet(currency.code, tz.key, today)
        b = _Builder(sheet)
        cur = currency.code

        # ---- monthly history: current month-to-date + last complete months
        months = []
        for delta in range(0, -(HISTORY_MONTHS + 1), -1):
            y, m = _shift(today.year, today.month, delta)
            months.append(
                await self.summary.period_summary(user.id, month_period(y, m, tz), currency)
            )
        current, complete = months[0], months[1:]

        for summary in [current, *complete]:
            label = summary.period.label
            suffix = " (месяц ещё не закончился)" if summary is current else ""
            t = summary.totals
            b.add("income", f"Доход за месяц{suffix}", t.income, cur, label)
            b.add(
                "expenses",
                f"Расходы за месяц (за вычетом возвратов){suffix}",
                t.net_expenses,
                cur,
                label,
            )
            b.add(
                "cash_flow", f"Чистый денежный поток за месяц{suffix}", t.net_cash_flow, cur, label
            )
            b.add("savings", f"Норма сбережений за месяц{suffix}", t.savings_rate, "%", label)

        with_data = [s for s in complete if s.totals.transaction_count > 0]
        if len(with_data) < 3:
            sheet.data_gaps.append("Меньше трёх полных месяцев с операциями: тренды ненадёжны.")
        if all(s.totals.income == 0 for s in complete):
            sheet.data_gaps.append("За последние месяцы не записано ни одного дохода.")

        last, before = complete[0], complete[1]
        b.add(
            "income",
            "Изменение дохода последнего полного месяца к предыдущему",
            percent_change(last.totals.income, before.totals.income),
            "%",
            last.period.label,
        )
        b.add(
            "expenses",
            "Изменение расходов последнего полного месяца к предыдущему",
            percent_change(last.totals.net_expenses, before.totals.net_expenses),
            "%",
            last.period.label,
        )
        avg_expenses = average([s.totals.net_expenses for s in complete[:3]], currency)
        b.add("expenses", "Средние расходы за 3 последних полных месяца", avg_expenses, cur)
        avg_income = average([s.totals.income for s in complete[:3]], currency)
        b.add("income", "Средний доход за 3 последних полных месяца", avg_income, cur)

        # ---- top expense categories of the last complete month
        period = last.period
        _, categories = await self.summary.category_breakdown(
            user.id, period.start, period.end, currency, "expense"
        )
        for item in categories[:TOP_CATEGORIES]:
            name = item.name if item.is_system else b.token("CAT", item.name)
            b.add("expenses", f"Расходы по категории «{name}»", item.amount, cur, period.label)
            b.add(
                "expenses",
                f"Доля категории «{name}» в расходах",
                item.share_percent,
                "%",
                period.label,
            )

        # ---- balances (accounts in this currency)
        accounts = await AccountService(self.db).list(user.id, include_archived=False)
        in_currency = [a for a in accounts if a.account.currency_code == cur]
        if in_currency:
            with calc_context():
                balance = quantize_money(
                    sum((a.balance for a in in_currency), Decimal(0)), currency
                )
            b.add("balance", "Текущий баланс счетов", balance, cur)
            if avg_expenses is not None:
                b.add(
                    "balance",
                    "На сколько месяцев средних расходов хватит баланса",
                    emergency_fund_months(balance, avg_expenses),
                    "months",
                )
        else:
            sheet.data_gaps.append(
                "Нет счетов в этой валюте: текущий баланс и финансовая подушка неизвестны."
            )

        # ---- budgets (current month, from transactions)
        budgets = list(
            await self.db.scalars(
                select(Budget)
                .where(Budget.user_id == user.id, Budget.currency_code == cur)
                .order_by(Budget.id)
            )
        )
        if not budgets:
            sheet.data_gaps.append("Бюджеты не заданы.")
        for budget in budgets:
            token = b.token("BUDGET", budget.title)
            u = await self.summary.budget_utilization(user.id, budget.id, today, tz)
            scope = "все расходы"
            if budget.category_id is not None:
                category = await self.db.get(Category, budget.category_id)
                if category is not None:
                    scope = (
                        category.name if category.user_id is None else b.token("CAT", category.name)
                    )
            label = f"Бюджет {token} ({scope})"
            b.add("budget", f"{label}: лимит", u.limit, cur, current.period.label)
            b.add("budget", f"{label}: потрачено", u.spent, cur, current.period.label)
            b.add(
                "budget", f"{label}: использовано", u.utilization_percent, "%", current.period.label
            )
            b.add(
                "budget",
                f"{label}: превышен",
                "да" if u.is_exceeded else "нет",
                "flag",
                current.period.label,
            )

        # ---- goals
        goals = list(
            await self.db.scalars(
                select(FinancialGoal).where(
                    FinancialGoal.user_id == user.id, FinancialGoal.currency_code == cur
                )
            )
        )
        if not goals:
            sheet.data_gaps.append("Финансовые цели не заданы.")
        for goal in goals:
            token = b.token("GOAL", goal.name)
            with calc_context():
                remaining = quantize_money(
                    max(goal.target_amount - goal.saved_amount, Decimal(0)), currency
                )
            b.add(
                "goal",
                f"Цель {token}: целевая сумма",
                quantize_money(goal.target_amount, currency),
                cur,
            )
            b.add(
                "goal", f"Цель {token}: накоплено", quantize_money(goal.saved_amount, currency), cur
            )
            b.add(
                "goal",
                f"Цель {token}: прогресс",
                share_percent(goal.saved_amount, goal.target_amount),
                "%",
            )
            b.add("goal", f"Цель {token}: осталось накопить", remaining, cur)
            if goal.target_date is not None:
                b.add("goal", f"Цель {token}: срок", goal.target_date.isoformat(), "date")
                months_left = months_until(today, goal.target_date)
                if months_left is None:
                    b.add("goal", f"Цель {token}: срок наступил или прошёл", "да", "flag")
                else:
                    b.add("goal", f"Цель {token}: месяцев до срока", months_left, "months")
                    b.add(
                        "goal",
                        f"Цель {token}: нужно откладывать в месяц (равными частями, без процентов)",
                        required_monthly_saving(remaining, months_left, currency),
                        cur,
                    )

        # ---- deposits
        deposits = list(
            await self.db.scalars(
                select(Deposit).where(Deposit.user_id == user.id, Deposit.currency_code == cur)
            )
        )
        for index, deposit in enumerate(deposits, start=1):
            maturity = maturity_of(deposit)
            label = f"Вклад {index}"
            b.add("deposit", f"{label}: сумма вклада", maturity.principal, cur)
            b.add(
                "deposit",
                f"{label}: номинальная ставка, указанная пользователем",
                deposit.interest_rate,
                "%",
            )
            if deposit.effective_rate is not None:
                b.add(
                    "deposit",
                    f"{label}: ГЭСВ по данным банка, указанная пользователем",
                    deposit.effective_rate,
                    "%",
                )
            b.add(
                "deposit",
                f"{label}: капитализация",
                _CAPITALIZATION_RU[deposit.capitalization],
                "text",
            )
            b.add("deposit", f"{label}: дата окончания", deposit.end_date.isoformat(), "date")
            b.add(
                "deposit",
                f"{label}: расчётный доход к концу срока (оценка)",
                maturity.interest,
                cur,
            )
            periods = PERIODS_PER_YEAR.get(deposit.capitalization)
            if periods:
                b.add(
                    "deposit",
                    f"{label}: эффективная годовая ставка с учётом капитализации (расчёт)",
                    effective_annual_rate(deposit.interest_rate, periods),
                    "%",
                )
        return sheet
