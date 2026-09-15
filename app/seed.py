from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal, init_db
from app.models import Account, MerchantRule, Setting
from app.taxonomy import DEFAULT_LIMITS, DEFAULT_SETTINGS

ACCOUNTS = [
    {"bank": "mono", "code": "black", "title": "Monobank чорна (кредит)", "external_id": ""},
    {"bank": "mono", "code": "white", "title": "Monobank біла", "external_id": ""},
    {"bank": "privat", "code": "salary", "title": "Приват зарплатна *6993", "external_id": "6993"},
    {"bank": "privat", "code": "credit", "title": "Приват кредитка *4038", "external_id": "4038"},
    {"bank": "privat", "code": "other", "title": "Приват *7977", "external_id": "7977"},
    {"bank": "cash", "code": "cash", "title": "Готівка (ручний ввід)", "external_id": "cash"},
]


async def seed() -> None:
    await init_db()
    from app.classify.rules import SEED_RULES

    async with SessionLocal() as session:
        for acc in ACCOUNTS:
            found = (
                await session.execute(
                    select(Account).where(Account.bank == acc["bank"], Account.code == acc["code"])
                )
            ).scalar_one_or_none()
            if not found:
                session.add(Account(**acc))

        for key, value in DEFAULT_SETTINGS.items():
            if await session.get(Setting, key) is None:
                session.add(Setting(key=key, value=value))
        if settings.telegram_user_id and await session.get(Setting, "telegram_user_id") is None:
            session.add(Setting(key="telegram_user_id", value=str(settings.telegram_user_id)))

        for cat, limit in DEFAULT_LIMITS.items():
            key = f"limit_{cat}"
            if await session.get(Setting, key) is None:
                session.add(Setting(key=key, value=str(limit)))

        for rule in SEED_RULES:
            exists = (
                await session.execute(
                    select(MerchantRule).where(MerchantRule.pattern == rule["pattern"])
                )
            ).scalar_one_or_none()
            if not exists:
                session.add(MerchantRule(**rule))

        await session.commit()
