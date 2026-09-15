from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.classify.llm import classify_llm
from app.classify.rules import classify_rules, fingerprint
from app.models import Account, MerchantRule, Setting, Transaction


async def get_account(session: AsyncSession, bank: str, code: str) -> Account:
    acc = (
        await session.execute(select(Account).where(Account.bank == bank, Account.code == code))
    ).scalar_one_or_none()
    if acc:
        return acc
    acc = Account(bank=bank, code=code, title=f"{bank} {code}", external_id="")
    session.add(acc)
    await session.flush()
    return acc


async def load_settings_map(session: AsyncSession) -> dict[str, str]:
    rows = (await session.execute(select(Setting))).scalars().all()
    return {r.key: r.value for r in rows}


async def extra_rules(session: AsyncSession) -> list[dict]:
    rows = (await session.execute(select(MerchantRule))).scalars().all()
    return [
        {
            "pattern": r.pattern,
            "category": r.category,
            "is_internal": r.is_internal,
            "is_essential": r.is_essential,
            "exclude_from_budget": r.exclude_from_budget,
        }
        for r in rows
    ]


async def ingest_items(
    session: AsyncSession,
    *,
    bank: str,
    account_code: str,
    source: str,
    items: list[dict],
    use_llm: bool = False,
) -> dict:
    acc = await get_account(session, bank, account_code)
    cfg = await load_settings_map(session)
    rules = await extra_rules(session)
    salary = Decimal(cfg.get("salary_target_uah", "40000"))
    dining_large = Decimal(cfg.get("dining_large_uah", "1200"))
    taxi_large = Decimal(cfg.get("taxi_large_uah", "500"))
    p2p_clarify = Decimal(cfg.get("p2p_clarify_uah", "200"))

    inserted = 0
    skipped = 0
    alerts: list[Transaction] = []
    for item in items:
        fp = fingerprint(
            f"{bank}:{account_code}",
            item["occurred_at"],
            Decimal(item["amount_uah"]),
            item["description"],
            item.get("mcc") or "",
        )
        exists = (
            await session.execute(select(Transaction.id).where(Transaction.fingerprint == fp))
        ).scalar_one_or_none()
        if exists:
            skipped += 1
            continue
        classified = classify_rules(
            description=item["description"],
            mcc=item.get("mcc") or "",
            amount=Decimal(item["amount_uah"]),
            bank_category=item.get("bank_category") or "",
            extra_rules=rules,
            salary_target=salary,
            dining_large=dining_large,
            taxi_large=taxi_large,
            p2p_clarify=p2p_clarify,
        )
        if (
            use_llm
            and classified.category == "UNCATEGORIZED_SUSPICIOUS"
            and abs(Decimal(item["amount_uah"])) >= Decimal("50")
        ):
            llm = await classify_llm(
                item["description"],
                item.get("mcc") or "",
                Decimal(item["amount_uah"]),
                item.get("bank_category") or "",
            )
            if llm and llm.category != "UNCATEGORIZED_SUSPICIOUS":
                classified.category = llm.category
                classified.confidence = llm.confidence
                classified.coach_comment = llm.coach_comment or classified.coach_comment
                classified.clarification_needed = llm.clarification_needed
                classified.clarification_title = llm.clarification_title
                classified.clarification_options = llm.clarification_options

        tx = Transaction(
            account_id=acc.id,
            source=source,
            fingerprint=fp,
            external_id=str(item.get("external_id") or ""),
            occurred_at=item["occurred_at"],
            description=item["description"],
            mcc=item.get("mcc") or "",
            amount_uah=Decimal(item["amount_uah"]),
            original_amount=item.get("original_amount"),
            original_currency=item.get("original_currency") or "UAH",
            fee_uah=Decimal(item.get("fee_uah") or 0),
            cashback_uah=Decimal(item.get("cashback_uah") or 0),
            balance_after=item.get("balance_after"),
            bank_category=item.get("bank_category") or "",
            card_mask=item.get("card_mask") or "",
            category=classified.category,
            confidence=classified.confidence,
            is_internal=classified.is_internal,
            exclude_from_budget=classified.exclude_from_budget,
            is_anomaly=classified.is_anomaly,
            is_essential=classified.is_essential,
            budget_impact=classified.budget_impact,
            clarification_needed=classified.clarification_needed,
            clarification_title=classified.clarification_title,
            clarification_options=classified.clarification_options,
            coach_comment=classified.coach_comment,
            raw={k: str(v) for k, v in item.items() if k != "occurred_at"},
        )
        session.add(tx)
        inserted += 1
        if classified.clarification_needed or (
            not classified.is_internal
            and not classified.exclude_from_budget
            and Decimal(item["amount_uah"]) < 0
            and (
                (classified.category == "DINING_LEISURE" and abs(Decimal(item["amount_uah"])) >= dining_large)
                or (classified.category == "TRANSIT_TAXI" and abs(Decimal(item["amount_uah"])) >= taxi_large)
            )
        ):
            alerts.append(tx)
    await session.commit()
    return {"inserted": inserted, "skipped": skipped, "alerts": alerts}
