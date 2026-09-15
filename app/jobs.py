from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.bot import get_bot
from app.bot.handlers import notify_new
from app.config import settings
from app.db import SessionLocal
from app.banks.monobank import sync_busy, sync_statements
from app.services.alerts import already_sent, mark_sent
from app.services.reports import debt_chart_png, weekly_text
from aiogram.types import BufferedInputFile

KYIV = ZoneInfo(settings.tz)
scheduler = AsyncIOScheduler(timezone=KYIV)


async def job_weekly():
    if not settings.telegram_bot_token or not settings.telegram_user_id:
        return
    fp = f"weekly:{datetime.now(KYIV).date().isoformat()}"
    async with SessionLocal() as session:
        if await already_sent(session, fp):
            return
        text = await weekly_text(session)
        png = await debt_chart_png(session)
        bot = get_bot()
        if png:
            await bot.send_photo(
                settings.telegram_user_id,
                BufferedInputFile(png, filename="debt.png"),
                caption=text[:1024],
            )
        else:
            await bot.send_message(settings.telegram_user_id, text[:4000])
        await mark_sent(session, fp, "weekly", None, {})


async def job_sync():
    if not settings.monobank_token or sync_busy():
        return
    async with SessionLocal() as session:
        result = await sync_statements(session, days=2)
        if result["alerts"] and settings.telegram_bot_token:
            await notify_new(get_bot(), result["alerts"], session)


def setup_jobs() -> None:
    scheduler.add_job(job_weekly, CronTrigger(day_of_week="sun", hour=20, minute=0, timezone=KYIV))
    if settings.monobank_token:
        scheduler.add_job(job_sync, IntervalTrigger(minutes=15))
    if not scheduler.running:
        scheduler.start()
