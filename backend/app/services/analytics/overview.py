from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import NotFoundError
from app.repositories.analytics import AnalyticsRepository, Scope
from app.repositories.cards import CardRepository
from app.schemas.analytics_overview import (
    AnalyticsOverview,
    BankShare,
    CardShare,
    CategoryShare,
    MerchantTotal,
    OverviewSummary,
    PeriodInfo,
    PeriodTotals,
    RecurringPayment,
    SeriesPoint,
    TopExpense,
    WeekdayTotal,
)
from app.services.analytics.periods import Period, bucket_label, bucket_starts, resolve_period
from app.services.finance.calendar import add_months
from app.services.finance.cashflow import growth_percent, savings_rate
from app.services.finance.money import ZERO, percent_or_zero, quantize_money

RECURRING_LOOKBACK_MONTHS = 6
TOP_LIMIT = 5


class AnalyticsOverviewService:
    """
    Сводная аналитика за период. Каждый блок — один агрегирующий
    SQL-запрос (всего ~10 запросов на ответ независимо от объёма данных).
    """

    def __init__(self, session: AsyncSession, today: date | None = None) -> None:
        self.repo = AnalyticsRepository(session)
        self.cards = CardRepository(session)
        self.today = today or date.today()

    async def overview(
        self,
        user_id: int,
        period: Period = Period.MONTH,
        date_from: date | None = None,
        date_to: date | None = None,
        card_id: int | None = None,
    ) -> AnalyticsOverview:
        if card_id is not None and await self.cards.get_owned(card_id, user_id) is None:
            raise NotFoundError("Card not found", code="CARD_NOT_FOUND")

        resolved = resolve_period(period, self.today, date_from, date_to)
        currency = settings.DEFAULT_CURRENCY
        scope = Scope(user_id, currency, resolved.date_from, resolved.date_to, card_id)
        prev_from, prev_to = resolved.previous
        prev_scope = Scope(user_id, currency, prev_from, prev_to, card_id)

        totals = await self.repo.totals(scope)
        previous = await self.repo.totals(prev_scope)
        rows = await self.repo.series(scope, resolved.granularity)
        categories = await self.repo.by_category(scope)
        merchants = await self.repo.top_merchants(scope, TOP_LIMIT)
        top_expenses = await self.repo.top_expenses(scope, TOP_LIMIT)
        banks = await self.repo.by_bank(scope)
        cards = await self.repo.by_card(scope)
        weekdays = await self.repo.by_weekday(scope)

        # Регулярные платежи ищем в окне 6 месяцев до конца периода:
        # в пределах дня или недели повторяемость не увидеть.
        recurring_from = datetime.combine(
            add_months(resolved.date_to.date(), -RECURRING_LOOKBACK_MONTHS), time.min
        )
        recurring = await self.repo.recurring(
            Scope(user_id, currency, recurring_from, resolved.date_to, card_id)
        )

        by_bucket = {bucket: (income, expense) for bucket, income, expense in rows}
        series = []
        for bucket in bucket_starts(resolved):
            income, expense = by_bucket.get(bucket, (ZERO, ZERO))
            series.append(
                SeriesPoint(
                    bucket=bucket,
                    label=bucket_label(bucket, resolved.granularity),
                    income=income,
                    expense=expense,
                    net=income - expense,
                )
            )

        return AnalyticsOverview(
            period=PeriodInfo(
                type=resolved.period,
                date_from=resolved.date_from,
                date_to=resolved.date_to,
                granularity=resolved.granularity,
                currency=currency,
            ),
            summary=OverviewSummary(
                income=totals.income,
                expense=totals.expense,
                net=totals.income - totals.expense,
                savings_rate=savings_rate(totals.income, totals.expense),
                income_count=totals.income_count,
                expense_count=totals.expense_count,
                average_daily_expense=quantize_money(totals.expense / Decimal(resolved.days)),
                previous=PeriodTotals(
                    income=previous.income,
                    expense=previous.expense,
                    net=previous.income - previous.expense,
                ),
                income_change_percent=growth_percent(totals.income, previous.income),
                expense_change_percent=growth_percent(totals.expense, previous.expense),
            ),
            series=series,
            categories=[
                CategoryShare(
                    category_id=category_id,
                    name=name,
                    color=color,
                    amount=amount,
                    share_percent=percent_or_zero(amount, totals.expense),
                    transaction_count=count,
                )
                for category_id, name, color, amount, count in categories
            ],
            top_merchants=[
                MerchantTotal(merchant=m, amount=amount, transaction_count=count)
                for m, amount, count in merchants
            ],
            top_expenses=[
                TopExpense(
                    transaction_id=t.id,
                    transaction_date=t.transaction_date,
                    amount=t.amount,
                    merchant=t.merchant or t.description,
                    category_id=t.category_id,
                )
                for t in top_expenses
            ],
            recurring=[
                RecurringPayment(merchant=m, amount=amount, occurrences=occ, months=months, last_date=last)
                for m, amount, occ, months, last in recurring
            ],
            banks=[
                BankShare(bank_id=bid, bank_name=name, income=inc, expense=exp, transaction_count=count)
                for bid, name, inc, exp, count in banks
            ],
            cards=[
                CardShare(card_id=cid, last4=last4, income=inc, expense=exp, transaction_count=count)
                for cid, last4, inc, exp, count in cards
            ],
            weekdays=[
                WeekdayTotal(weekday=wd, amount=amount, transaction_count=count)
                for wd, amount, count in weekdays
            ],
        )
