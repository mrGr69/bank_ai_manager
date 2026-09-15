from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Awaitable, Callable

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Account
from app.services.ingest import ingest_items, get_account

BASE = "https://api.monobank.ua"
MONO_GAP_SEC = 62.0
SYNC_TIMEOUT_SEC = 8 * 60
log = logging.getLogger("uvicorn.error")

Progress = Callable[[str], Awaitable[None]]


class MonoError(RuntimeError):
    pass


_last_mono_at = 0.0
_sync_lock = asyncio.Lock()
_sync_started_at: float | None = None


def sync_busy() -> bool:
    return _sync_lock.locked()


def sync_running_seconds() -> int:
    if _sync_started_at is None:
        return 0
    return max(0, int(time.monotonic() - _sync_started_at))


async def _throttle() -> None:
    global _last_mono_at
    wait = MONO_GAP_SEC - (time.monotonic() - _last_mono_at)
    if wait > 0:
        log.info("monobank throttle %.0fs", wait)
        await asyncio.sleep(wait)


async def _get(path: str) -> dict | list:
    global _last_mono_at
    if not settings.monobank_token:
        raise MonoError("MONOBANK_TOKEN порожній")
    last_error = None
    for attempt in range(2):
        await _throttle()
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f"{BASE}{path}", headers={"X-Token": settings.monobank_token})
            _last_mono_at = time.monotonic()
            if r.status_code == 429:
                last_error = MonoError("Monobank rate limit, зачекай хвилину")
                log.warning("monobank 429 on %s, retry", path)
                continue
            if r.status_code >= 400:
                raise MonoError(f"Monobank {r.status_code}: {r.text[:200]}")
            return r.json()
    raise last_error or MonoError("Monobank rate limit, зачекай хвилину")


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


def compute_mono_debt(balance: Decimal, credit_limit: Decimal | None) -> Decimal:
    """Monobank balance includes credit. Own = balance - limit; debt = -own if negative."""
    limit = credit_limit or Decimal("0")
    own = balance - limit
    if own < 0:
        return (-own).quantize(Decimal("0.01"))
    return Decimal("0.00")


def assign_mono_codes(accounts: list[dict]) -> list[tuple[dict, str]]:
    """One DB row per UAH account. Seeded black/white bind to the real cards, not the last extra jar."""
    uah = [a for a in accounts if a.get("currencyCode") in (980, "980")]

    def sort_key(raw: dict):
        t = str(raw.get("type") or "").lower()
        limit = int(raw.get("creditLimit") or 0)
        if t == "black":
            return (0, -limit)
        if "white" in t:
            return (1, 0)
        return (2, -limit)

    used: set[str] = set()
    out: list[tuple[dict, str]] = []
    for raw in sorted(uah, key=sort_key):
        t = str(raw.get("type") or "acc").lower() or "acc"
        t = "".join(ch if ch.isalnum() else "_" for ch in t)[:20]
        if t == "black" and "black" not in used:
            code = "black"
        elif "white" in t and "white" not in used:
            code = "white"
        else:
            suffix = str(raw.get("id") or "x")[-6:]
            code = f"{t}_{suffix}"[:32]
            n = 2
            while code in used:
                code = f"{t}_{suffix}{n}"[:32]
                n += 1
        used.add(code)
        out.append((raw, code))
    return out


def guess_code(acc: dict) -> str:
    assigned = assign_mono_codes([acc])
    return assigned[0][1] if assigned else "black"


def mono_title(raw: dict, code: str) -> str:
    if code == "black":
        return "Monobank чорна (кредит)"
    if code == "white":
        return "Monobank біла"
    pans = raw.get("maskedPan") or []
    tail = str(pans[0])[-4:] if pans else ""
    kind = raw.get("type") or code
    return " ".join(part for part in (f"Monobank {kind}", tail) if part)


async def sync_accounts(session: AsyncSession) -> list[Account]:
    info = await client_info()
    now = datetime.now(timezone.utc)
    updated = []
    for raw, code in assign_mono_codes(info.get("accounts") or []):
        acc = await get_account(session, "mono", code)
        acc.external_id = raw.get("id") or acc.external_id
        acc.credit_limit_uah = _kopiyka(raw.get("creditLimit"))
        balance = _kopiyka(raw.get("balance"))
        acc.last_balance_uah = balance
        acc.last_debt_uah = compute_mono_debt(balance, acc.credit_limit_uah)
        acc.last_synced_at = now
        acc.title = mono_title(raw, code)
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


def should_fetch_statement(acc: Account) -> bool:
    if not acc.external_id:
        return False
    if acc.code in {"black", "white"}:
        return True
    return (acc.credit_limit_uah or Decimal("0")) > 0


async def sync_statements(
    session: AsyncSession | None = None,
    days: int = 31,
    progress: Progress | None = None,
    use_llm: bool = False,
) -> dict:
    if _sync_lock.locked():
        raise MonoError(f"Уже йде синк ({sync_running_seconds()} с). Зачекай.")
    global _sync_started_at
    async with _sync_lock:
        _sync_started_at = time.monotonic()
        try:
            return await asyncio.wait_for(
                _sync_statements_inner(days=days, progress=progress, use_llm=use_llm),
                timeout=SYNC_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError as exc:
            raise MonoError("Синк зупинено: зависання довше 8 хв. Натисни /sync ще раз.") from exc
        finally:
            _sync_started_at = None


async def _sync_statements_inner(
    *, days: int, progress: Progress | None, use_llm: bool
) -> dict:
    from sqlalchemy import select
    from app.db import SessionLocal

    async with SessionLocal() as session:
        updated = await sync_accounts(session)
        credits = [
            a for a in updated if (a.credit_limit_uah or Decimal("0")) > 0 or (a.last_debt_uah or 0) > 0
        ]
        if progress:
            if credits:
                bits = [f"{a.title}: {a.last_debt_uah} / {a.credit_limit_uah} ₴" for a in credits]
                await progress("Ліміти оновлено.\n" + "\n".join(bits))
            else:
                await progress("Ліміти оновлено. Кредитних карток з лімітом не видно.")
        rows = (await session.execute(select(Account).where(Account.bank == "mono"))).scalars().all()
        targets = [(acc.code, acc.external_id, acc.title) for acc in rows if should_fetch_statement(acc)]

    total = {"inserted": 0, "skipped": 0, "alerts": []}
    for i, (code, external_id, title) in enumerate(targets, 1):
        if progress:
            await progress(f"Виписка {i}/{len(targets)}: {title}…")
        log.info("monobank statement %s/%s %s", i, len(targets), code)
        items = await fetch_statement(external_id, days=days)
        async with SessionLocal() as session:
            result = await ingest_items(
                session, bank="mono", account_code=code, source="mono_api", items=items, use_llm=use_llm
            )
        total["inserted"] += result["inserted"]
        total["skipped"] += result["skipped"]
        total["alerts"].extend(result["alerts"])
    return total
