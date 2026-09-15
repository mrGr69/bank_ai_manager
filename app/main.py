from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.bot import get_bot
from app.bot.handlers import dp, notify_new
from app.config import settings
from app.db import SessionLocal, init_db
from app.jobs import setup_jobs
from app.seed import seed
from app.banks.monobank import set_webhook, sync_accounts
from aiogram.types import Update


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await seed()
    setup_jobs()
    polling_task = None
    if settings.telegram_bot_token:
        bot = get_bot()
        if settings.public_url:
            await bot.set_webhook(
                settings.public_url.rstrip("/") + "/telegram/webhook",
                secret_token=None,
            )
            if settings.monobank_token:
                try:
                    await set_webhook(settings.public_url.rstrip("/") + "/hooks/monobank")
                    async with SessionLocal() as session:
                        await sync_accounts(session)
                except Exception:
                    pass
        else:
            import asyncio

            polling_task = asyncio.create_task(dp.start_polling(bot))
    yield
    if polling_task:
        polling_task.cancel()
    if settings.telegram_bot_token and settings.public_url:
        try:
            await get_bot().delete_webhook()
        except Exception:
            pass


app = FastAPI(title="Sentinel", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    if not settings.telegram_bot_token:
        return Response(status_code=503)
    payload = await request.json()
    update = Update.model_validate(payload, context={"bot": get_bot()})
    await dp.feed_update(get_bot(), update)
    return {"ok": True}


@app.get("/hooks/monobank")
async def monobank_webhook_verify():
    # Monobank sends GET to confirm the URL; must be HTTP 200.
    return Response(status_code=200)


@app.post("/hooks/monobank")
async def monobank_webhook(request: Request):
    payload = await request.json()
    # Immediate 200: process after? Monobank wants 200 in 5s. We process inline if small.
    from datetime import datetime, timezone
    from app.banks.monobank import _kopiyka
    from app.services.ingest import ingest_items, get_account

    data = payload.get("data") or {}
    item = data.get("statementItem") or {}
    account_id = data.get("account")
    if not item:
        return JSONResponse({"ok": True})
    async with SessionLocal() as session:
        from sqlalchemy import select
        from app.models import Account

        acc = (
            await session.execute(select(Account).where(Account.external_id == str(account_id)))
        ).scalar_one_or_none()
        code = acc.code if acc else "black"
        mapped = {
            "occurred_at": datetime.fromtimestamp(item.get("time") or 0, tz=timezone.utc),
            "description": item.get("description") or "",
            "mcc": str(item.get("mcc") or ""),
            "amount_uah": _kopiyka(item.get("amount")),
            "original_amount": _kopiyka(item.get("operationAmount")),
            "original_currency": str(item.get("currencyCode") or ""),
            "fee_uah": _kopiyka(item.get("commissionRate")),
            "cashback_uah": _kopiyka(item.get("cashbackAmount")),
            "balance_after": _kopiyka(item.get("balance")),
            "external_id": item.get("id") or "",
        }
        result = await ingest_items(
            session, bank="mono", account_code=code, source="mono_webhook", items=[mapped], use_llm=True
        )
        if result["alerts"] and settings.telegram_bot_token and settings.telegram_user_id:
            await notify_new(get_bot(), result["alerts"], session)
    return JSONResponse({"ok": True})
