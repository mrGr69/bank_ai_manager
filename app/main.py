from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.bot import get_bot
from app.bot.handlers import dp, notify_new
from app.bot.updates import remember_update, spawn
from app.config import settings
from app.db import SessionLocal, init_db
from app.jobs import setup_jobs
from app.seed import seed
from app.banks.monobank import set_webhook, sync_accounts
from aiogram.types import BotCommand, Update

log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await seed()
    setup_jobs()
    polling_task = None
    if settings.telegram_bot_token:
        bot = get_bot()
        if settings.public_url:
            webhook_url = settings.public_url.rstrip("/") + "/telegram/webhook"
            await bot.set_webhook(
                webhook_url,
                allowed_updates=["message", "callback_query"],
                drop_pending_updates=False,
            )
            await bot.set_my_commands(
                [
                    BotCommand(command="start", description="Показати кнопки"),
                    BotCommand(command="status", description="Місяць"),
                    BotCommand(command="debt", description="Борги"),
                    BotCommand(command="week", description="Тиждень"),
                    BotCommand(command="sync", description="Синк Monobank"),
                ]
            )
            log.info(
                "telegram webhook=%s owner_id=%s",
                webhook_url,
                settings.telegram_user_id,
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


app = FastAPI(title="Sentinel", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    if not settings.telegram_bot_token:
        return Response(status_code=503)
    payload = await request.json()
    msg = payload.get("message") or payload.get("edited_message") or {}
    from_user = msg.get("from") or payload.get("callback_query", {}).get("from") or {}
    log.info(
        "telegram update_id=%s keys=%s from_id=%s chat_id=%s text=%r",
        payload.get("update_id"),
        list(payload.keys()),
        from_user.get("id"),
        (msg.get("chat") or {}).get("id"),
        (msg.get("text") or "")[:80],
    )
    update_id = payload.get("update_id")
    if not remember_update(update_id):
        log.info("telegram duplicate update_id=%s ignored", update_id)
        return {"ok": True}

    async def _run():
        try:
            bot = get_bot()
            update = Update.model_validate(payload, context={"bot": bot})
            await dp.feed_update(bot, update)
        except Exception:
            log.exception("telegram webhook failed")

    spawn(_run())
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
