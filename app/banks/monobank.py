from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Account
from app.services.ingest import ingest_items, get_account

BASE = "https://api.monobank.ua"


class MonoError(RuntimeError):
    pass


async def _get(path: str) -> dict | list:
    if not settings.monobank_token:
        raise MonoError("MONOBANK_TOKEN порожній")
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{BASE}{path}", headers={"X-Token": settings.monobank_token})
        if r.status_code == 429:
            raise MonoError("Monobank rate limit, зачекай хвилину")
        if r.status_code >= 400:
            raise MonoError(f"Monobank {r.status_code}: {r.text[:200]}")
        return r.json()


async def client_info() -> dict:
    return await _get("/personal/client-info")


async def set_webhook(url: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            f"{BASE}/personal/webhook",
            headers={"X-Token": settings.monobank_token, "Content-Type": "application/json"},
            json={"webHookUrl": url},
        )
        r.raise_for_status()
        return r.json() if r.content else {}


def _kopiyka(value) -> Decimal:
    return (Decimal(value or 0) / Decimal(100)).quantize(Decimal("0.01"))


def guess_code(acc: dict) -> str:
    if acc.get("type") == "white" or "white" in str(acc.get("type", "")).lower():
        return "white"
    return "black"


async def sync_accounts(session: AsyncSession) -> list[Account]:
    info = await client_info()
    now = datetime.now(timezone.utc)
    updated = []
    for raw in info.get("accounts") or []:
        if raw.get("currencyCode") not in (980, "980"):
            continue
        code = guess_code(raw)
        acc = await get_account(session, "mono", code)
        acc.external_id = raw.get("id") or acc.external_id
        acc.credit_limit_uah = _kopiyka(raw.get("creditLimit"))
        balance = _kopiyka(raw.get("balance"))
        acc.last_balance_uah = balance
        # Monobank: debt ≈ creditLimit - own funds. If balance < creditLimit, used credit = creditLimit - balance
        # when using credit, balance is own+credit remaining. Debt = creditLimit - max(balance, 0) if balance is available including credit.
        # Docs: balance includes credit. Available own = balance - creditLimit (can be negative).
        # Debt = creditLimit - (balance) if we think of leftover credit... 
        # Actually: total = balance (available to spend). creditLimit = credit. Own = balance - creditLimit.
        # If own < 0, debt = -own.
        own = balance - (acc.credit_limit_uah or 0)
        acc.last_debt_uah = -own if own < 0 else Decimal("0")
        acc.last_synced_at = now
        if not acc.title:
            acc.title = f"Monobank {code}"
        updated.append(acc)
    await session.commit()
    return updated


async def fetch_statement(account_id: str, days: int = 31) -> list[dict]:
    now = datetime.now(timezone.utc)
    frm = int((now - timedelta(days=min(days, 31))).timestamp())
    to = int(now.timestamp())
    data = await _get(f"/personal/statement/{account_id}/{frm}/{to}")
    items = []
    for raw in data or []:
        items.append(
            {
                "occurred_at": datetime.fromtimestamp(raw["time"], tz=timezone.utc),
                "description": raw.get("description") or "",
                "mcc": str(raw.get("mcc") or ""),
                "amount_uah": _kopiyka(raw.get("amount")),
                "original_amount": _kopiyka(raw.get("operationAmount")),
                "original_currency": str(raw.get("currencyCode") or "980"),
                "fee_uah": _kopiyka(raw.get("commissionRate")),
                "cashback_uah": _kopiyka(raw.get("cashbackAmount")),
                "balance_after": _kopiyka(raw.get("balance")),
                "external_id": raw.get("id") or "",
                "bank_category": "",
                "card_mask": "",
            }
        )
    return items


async def sync_statements(session: AsyncSession, days: int = 31) -> dict:
    from sqlalchemy import select

    await sync_accounts(session)
    await asyncio.sleep(61)
    accounts = (await session.execute(select(Account).where(Account.bank == "mono"))).scalars().all()
    total = {"inserted": 0, "skipped": 0, "alerts": []}
    waited = False
    for acc in accounts:
        if not acc.external_id:
            continue
        if waited:
            await asyncio.sleep(61)
        waited = True
        items = await fetch_statement(acc.external_id, days=days)
        result = await ingest_items(
            session, bank="mono", account_code=acc.code, source="mono_api", items=items, use_llm=True
        )
        total["inserted"] += result["inserted"]
        total["skipped"] += result["skipped"]
        total["alerts"].extend(result["alerts"])
    return total
