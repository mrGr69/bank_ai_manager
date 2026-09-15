from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    ErrorEvent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
)
from sqlalchemy import select

from app.config import parse_telegram_user_id, settings
from app.db import SessionLocal
from app.models import Setting, Transaction
from app.banks.monobank import MonoError, sync_statements
from app.services.files import import_path
from app.services.alerts import mark_sent, should_alert_limit, already_sent
from app.services.ledger import category_label, debt_snapshot, fmt_money, month_summary
from app.services.reports import debt_chart_png, weekly_text
from app.taxonomy import CATEGORIES

log = logging.getLogger("uvicorn.error")
router = Router()
dp = Dispatcher()


def allowed(user_id: int | None) -> bool:
    expected = parse_telegram_user_id(settings.telegram_user_id)
    if expected is None:
        return True
    got = parse_telegram_user_id(user_id)
    return got == expected


class OwnerOnlyMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        uid = getattr(user, "id", None)
        if allowed(uid):
            return await handler(event, data)
        log.warning("telegram ignore user_id=%s expected=%s", uid, settings.telegram_user_id)
        bot = data.get("bot")
        if isinstance(event, Message) and bot is not None:
            await bot.send_message(
                event.chat.id,
                f"Немає доступу. Твій Telegram id: {uid}",
            )
        elif isinstance(event, CallbackQuery):
            await event.answer("Немає доступу", show_alert=True)
        return None


router.message.middleware(OwnerOnlyMiddleware())
router.callback_query.middleware(OwnerOnlyMiddleware())
dp.include_router(router)


@dp.error()
async def on_telegram_error(event: ErrorEvent):
    log.exception("telegram handler crashed: %s", event.exception)


def kb_clarify(tx: Transaction) -> InlineKeyboardMarkup | None:
    opts = tx.clarification_options or []
    if not opts:
        return None
    rows = []
    for opt in opts:
        cat = opt.get("cat") or ""
        label = opt.get("label") or cat
        rows.append([InlineKeyboardButton(text=label[:40], callback_data=f"fix:{tx.id}:{cat}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_tx(tx: Transaction) -> str:
    sign = tx.amount_uah
    return (
        f"{fmt_money(sign)}\n"
        f"{tx.description}\n"
        f"{category_label(tx.category)} · {tx.coach_comment}"
    )


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "Sentinel на зв'язку. Я дивлюсь зовнішні витрати, борги і діри в категоріях.\n\n"
        "/status — місяць\n"
        "/debt — кредитки\n"
        "/sync — підтягнути Monobank\n"
        "/salary 40000 — орієнтир доходу\n"
        "/income 12000 — готівкова зарплата\n"
        "/limit DINING_LEISURE 6000\n"
        "Кинь Excel виписки Привату — імпортую."
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await cmd_start(message)


@router.message(Command("status"))
async def cmd_status(message: Message):
    async with SessionLocal() as session:
        s = await month_summary(session)
    lines = [
        f"Орієнтир: {fmt_money(s['salary_target'])}",
        f"Надходження: {fmt_money(s['income'])}",
        f"Витрати: {fmt_money(s['spent'])}",
        f"Відносно орієнтиру: {fmt_money(s['free'])}",
        "",
        f"Кафе: {fmt_money(s['leaks']['DINING_LEISURE'])}",
        f"Таксі: {fmt_money(s['leaks']['TRANSIT_TAXI'])}",
        f"Дейтинг: {fmt_money(s['leaks']['DATING_ROMANCE'])}",
    ]
    await message.answer("\n".join(lines))


@router.message(Command("debt"))
async def cmd_debt(message: Message):
    async with SessionLocal() as session:
        debts = await debt_snapshot(session)
        png = await debt_chart_png(session)
        text_lines = []
        for d in debts:
            text_lines.append(f"{d['title']}: борг {fmt_money(d['debt'])} / ліміт {fmt_money(d['limit'])}")
        if not text_lines:
            text_lines = ["Боргів у профілі ще немає. Зроби /sync або кинь виписку."]
        else:
            text_lines.append("\nПропозиція: зарплата спочатку на моно-борг (грейс), дрібниці — з білої/кешу, не з кредитки Привату.")
        if png:
            await message.answer_photo(
                BufferedInputFile(png, filename="debt.png"),
                caption="\n".join(text_lines),
            )
        else:
            await message.answer("\n".join(text_lines))


@router.message(Command("week"))
async def cmd_week(message: Message):
    async with SessionLocal() as session:
        text = await weekly_text(session)
        png = await debt_chart_png(session)
    if png:
        await message.answer_photo(BufferedInputFile(png, filename="debt.png"), caption=text[:1024])
        if len(text) > 1024:
            await message.answer(text[1024:4000])
    else:
        await message.answer(text[:4000])


@router.message(Command("salary"))
async def cmd_salary(message: Message, command: CommandObject):
    if not command.args:
        async with SessionLocal() as session:
            row = await session.get(Setting, "salary_target_uah")
        await message.answer(f"Поточний орієнтир: {row.value if row else '40000'} ₴. Приклад: /salary 40000")
        return
    raw = command.args.replace(" ", "").replace("₴", "")
    try:
        value = str(int(Decimal(raw)))
    except Exception:
        await message.answer("Потрібне число, наприклад /salary 40000")
        return
    async with SessionLocal() as session:
        row = await session.get(Setting, "salary_target_uah")
        if row:
            row.value = value
        else:
            session.add(Setting(key="salary_target_uah", value=value))
        await session.commit()
    await message.answer(f"Орієнтир зарплати: {value} ₴. Міняється без деплою.")


@router.message(Command("income"))
async def cmd_income(message: Message, command: CommandObject):
    parts = (command.args or "").split(maxsplit=1)
    if not parts:
        await message.answer("Готівкова зарплата: /income 12000")
        return
    try:
        amount = Decimal(parts[0].replace(",", "."))
    except Exception:
        await message.answer("Потрібне число: /income 12000")
        return
    note = parts[1] if len(parts) > 1 else "Готівкова зарплата (ручний ввід)"
    from datetime import datetime, timezone
    from app.services.ingest import ingest_items

    async with SessionLocal() as session:
        result = await ingest_items(
            session,
            bank="cash",
            account_code="cash",
            source="manual",
            items=[
                {
                    "occurred_at": datetime.now(timezone.utc),
                    "description": note,
                    "mcc": "",
                    "amount_uah": amount,
                    "bank_category": "Зарахування",
                }
            ],
        )
    await message.answer(f"Записав надходження {amount} ₴ ({result['inserted']} нових).")


@router.message(Command("limit"))
async def cmd_limit(message: Message, command: CommandObject):
    parts = (command.args or "").split()
    if len(parts) != 2:
        await message.answer(
            "Формат: /limit DINING_LEISURE 6000\nКатегорії: " + ", ".join(sorted(CATEGORIES))
        )
        return
    cat, amt = parts[0].upper(), parts[1]
    if cat not in CATEGORIES:
        await message.answer("Невідома категорія")
        return
    async with SessionLocal() as session:
        key = f"limit_{cat}"
        row = await session.get(Setting, key)
        if row:
            row.value = amt
        else:
            session.add(Setting(key=key, value=amt))
        await session.commit()
    await message.answer(f"Ліміт {category_label(cat)}: {amt} ₴")


@router.message(Command("sync"))
async def cmd_sync(message: Message):
    await message.answer("Тягну Monobank. Через ліміт банку це може зайняти ~2 хв…")
    try:
        async with SessionLocal() as session:
            result = await sync_statements(session, days=31)
            await notify_new(message.bot, result["alerts"], session)
        await message.answer(
            f"Готово: нових {result['inserted']}, уже були {result['skipped']}."
        )
    except MonoError as exc:
        await message.answer(str(exc))


@router.message(F.document)
async def on_document(message: Message, bot: Bot):
    doc = message.document
    name = (doc.file_name or "file.xlsx").lower()
    if not name.endswith((".xlsx", ".xls", ".csv")):
        await message.answer("Потрібен Excel/CSV виписки.")
        return
    await message.answer("Читаю виписку…")
    import tempfile

    dest = Path(tempfile.gettempdir()) / (doc.file_name or "statement.xlsx")
    await bot.download(doc, destination=dest)
    async with SessionLocal() as session:
        result = await import_path(session, dest)
        await notify_new(bot, result.get("alerts") or [], session)
    dest.unlink(missing_ok=True)
    await message.answer(
        f"Імпорт ({result.get('kind')}): нових {result['inserted']}, дублі {result['skipped']}."
    )


@router.callback_query(F.data.startswith("fix:"))
async def on_fix(query: CallbackQuery):
    _, tx_id, cat = query.data.split(":", 2)
    async with SessionLocal() as session:
        tx = await session.get(Transaction, int(tx_id))
        if not tx:
            await query.answer("Вже немає")
            return
        tx.category = cat
        tx.clarification_needed = False
        tx.is_internal = False
        if cat == "ONE_OFF":
            tx.exclude_from_budget = True
        await session.commit()
    await query.answer("Ок")
    if query.message:
        await query.message.edit_reply_markup(reply_markup=None)
        await query.message.answer(f"Записав як {category_label(cat)}.")


@router.message()
async def on_other(message: Message):
    text = (message.text or "").strip()
    log.info("unhandled telegram text=%r chat=%s", text[:80], message.chat.id if message.chat else None)
    if text.startswith("/"):
        await message.answer("Невідома команда. Напиши /start")


async def notify_new(bot: Bot, transactions: list[Transaction], session):
    if not settings.telegram_user_id:
        return
    for tx in transactions:
        if tx.id is None:
            continue
        fp = f"tx:{tx.id}"
        if await already_sent(session, fp):
            continue
        limit_msg = await should_alert_limit(session, tx)
        text = format_tx(tx)
        if tx.clarification_title:
            text = tx.clarification_title + "\n\n" + text
        if limit_msg:
            text += "\n\n⚠️ " + limit_msg
        await bot.send_message(
            settings.telegram_user_id,
            text[:4000],
            reply_markup=kb_clarify(tx),
        )
        await mark_sent(session, fp, "tx", tx, {"category": tx.category})
