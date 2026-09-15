from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AlertLog, Setting, Transaction
from app.services.ledger import category_month_spent, fmt_money
from app.taxonomy import LEAK_CATEGORIES


async def should_alert_limit(session: AsyncSession, tx: Transaction) -> str | None:
    if tx.is_internal or tx.exclude_from_budget or tx.amount_uah >= 0:
        return None
    if tx.category not in LEAK_CATEGORIES:
        return None
    key = f"limit_{tx.category}"
    row = await session.get(Setting, key)
    if not row:
        return None
    limit = Decimal(row.value)
    spent = await category_month_spent(session, tx.category, tx.occurred_at)
    # spent is negative
    if abs(spent) >= limit:
        return (
            f"Ліміт {tx.category} {fmt_money(limit)} на місяць уже пробито: "
            f"{fmt_money(spent)} з урахуванням цієї операції."
        )
    return None


async def already_sent(session: AsyncSession, fingerprint: str) -> bool:
    row = (
        await session.execute(select(AlertLog.id).where(AlertLog.fingerprint == fingerprint))
    ).scalar_one_or_none()
    return row is not None


async def mark_sent(session: AsyncSession, fingerprint: str, kind: str, tx: Transaction | None, payload: dict):
    session.add(
        AlertLog(
            transaction_id=tx.id if tx else None,
            kind=kind,
            fingerprint=fingerprint,
            payload=payload,
        )
    )
    await session.commit()
