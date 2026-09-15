from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Account, Setting, Transaction
from app.taxonomy import CATEGORIES, LEAK_CATEGORIES

KYIV = ZoneInfo(settings.tz)


def month_bounds(when: datetime | None = None) -> tuple[datetime, datetime]:
    now = (when or datetime.now(KYIV)).astimezone(KYIV)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


async def setting_decimal(session: AsyncSession, key: str, default: str) -> Decimal:
    row = await session.get(Setting, key)
    return Decimal((row.value if row else default) or default)


async def visible_filter():
    return (
        Transaction.is_internal.is_(False),
        Transaction.exclude_from_budget.is_(False),
    )


async def month_summary(session: AsyncSession, when: datetime | None = None) -> dict:
    start, end = month_bounds(when)
    vis = await visible_filter()
    rows = (
        await session.execute(
            select(Transaction.category, func.sum(Transaction.amount_uah), func.count())
            .where(Transaction.occurred_at >= start, Transaction.occurred_at < end, *vis)
            .group_by(Transaction.category)
        )
    ).all()
    by_cat = {cat: {"sum": Decimal(total or 0), "n": n} for cat, total, n in rows}
    income = Decimal("0")
    spent = Decimal("0")
    for cat, data in by_cat.items():
        if data["sum"] > 0:
            income += data["sum"]
        else:
            spent += data["sum"]
    salary_target = await setting_decimal(session, "salary_target_uah", "40000")
    leaks = {
        cat: by_cat.get(cat, {"sum": Decimal("0"), "n": 0})["sum"] for cat in LEAK_CATEGORIES
    }
    return {
        "start": start,
        "end": end,
        "income": income,
        "spent": spent,
        "by_cat": by_cat,
        "salary_target": salary_target,
        "leaks": leaks,
        "free": salary_target + spent,  # spent is negative
    }


async def category_month_spent(session: AsyncSession, category: str, when: datetime | None = None) -> Decimal:
    start, end = month_bounds(when)
    vis = await visible_filter()
    total = (
        await session.execute(
            select(func.coalesce(func.sum(Transaction.amount_uah), 0)).where(
                Transaction.occurred_at >= start,
                Transaction.occurred_at < end,
                Transaction.category == category,
                *vis,
            )
        )
    ).scalar_one()
    return Decimal(total)


async def debt_snapshot(session: AsyncSession) -> list[dict]:
    accounts = (await session.execute(select(Account).order_by(Account.bank, Account.code))).scalars().all()
    out = []
    for acc in accounts:
        limit = acc.credit_limit_uah or Decimal("0")
        debt = acc.last_debt_uah or Decimal("0")
        if limit <= 0 and debt <= 0:
            continue
        out.append(
            {
                "title": acc.title,
                "bank": acc.bank,
                "code": acc.code,
                "limit": acc.credit_limit_uah or Decimal("0"),
                "debt": debt,
                "balance": acc.last_balance_uah,
                "synced": acc.last_synced_at,
            }
        )
    return out


def fmt_money(value: Decimal | int | float | None) -> str:
    if value is None:
        return "—"
    v = Decimal(value)
    sign = "-" if v < 0 else ""
    return f"{sign}{abs(v):,.2f} ₴".replace(",", " ")


def category_label(code: str) -> str:
    return CATEGORIES.get(code, code)
