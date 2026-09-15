from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    ErrorEvent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    TelegramObject,
)
from sqlalchemy import select

from app.config import parse_telegram_user_id, settings
from app.db import SessionLocal
from app.models import Setting, Transaction
from app.banks.monobank import MonoError, sync_busy, sync_running_seconds, sync_statements
from app.services.files import import_path
from app.services.alerts import mark_sent, should_alert_limit, already_sent
from app.services.ledger import category_label, debt_snapshot, fmt_money
from app.services.reports import debt_chart_png, month_text, weekly_text
from app.taxonomy import CATEGORIES, all_category_options

log = logging.getLogger("uvicorn.error")
router = Router()
dp = Dispatcher(storage=MemoryStorage())


class Form(StatesGroup):
    limit_amount = State()
    salary = State()
    income = State()


BTN_STATUS = "Місяць"
BTN_DEBT = "Борги"
BTN_WEEK = "Тиждень"
BTN_SYNC = "Синк Моно"
BTN_LIMITS = "Ліміти"
BTN_SALARY = "Орієнтир"
BTN_INCOME = "Готівка"
MENU_BUTTONS = {BTN_STATUS, BTN_DEBT, BTN_WEEK, BTN_SYNC, BTN_LIMITS, BTN_SALARY, BTN_INCOME}


def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_STATUS), KeyboardButton(text=BTN_DEBT), KeyboardButton(text=BTN_WEEK)],
            [KeyboardButton(text=BTN_SYNC), KeyboardButton(text=BTN_LIMITS)],
            [KeyboardButton(text=BTN_SALARY), KeyboardButton(text=BTN_INCOME)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def kb_limit_cats() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for code, label in CATEGORIES.items():
        if code == "INCOME_SALARY":
            continue
        row.append(InlineKeyboardButton(text=label[:32], callback_data=f"lim:{code}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
    if tx.category == "UNCATEGORIZED_SUSPICIOUS":
        opts = all_category_options()
    else:
        opts = tx.clarification_options or []
    if not opts:
        return None
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for opt in opts:
        cat = opt.get("cat") or ""
        label = opt.get("label") or category_label(cat)
        row.append(InlineKeyboardButton(text=label[:40], callback_data=f"fix:{tx.id}:{cat}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_tx(tx: Transaction) -> str:
    sign = tx.amount_uah
    return (
        f"{fmt_money(sign)}\n"
        f"{tx.description}\n"
        f"{category_label(tx.category)} · {tx.coach_comment}"
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Sentinel на зв'язку. Дивлюсь зовнішні витрати, борги і діри в категоріях.\n\n"
        "Кнопки внизу: «Місяць» — з 1 числа; «Тиждень» — з понеділка.\n"
        "Орієнтир — плановий дохід. Готівка — ручне надходження.\n"
        "Excel виписки Привату кидай файлом у чат.",
        reply_markup=main_kb(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext):
    await cmd_start(message, state)


@router.message(Command("status"))
async def cmd_status(message: Message):
    async with SessionLocal() as session:
        text = await month_text(session)
    await message.answer(text[:4000], reply_markup=main_kb())


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
                reply_markup=main_kb(),
            )
        else:
            await message.answer("\n".join(text_lines), reply_markup=main_kb())


@router.message(Command("week"))
async def cmd_week(message: Message):
    async with SessionLocal() as session:
        text = await weekly_text(session)
    await message.answer(text[:4000], reply_markup=main_kb())


async def save_salary(message: Message, raw: str) -> None:
    value = str(int(Decimal(raw.replace(" ", "").replace("₴", "").replace(",", "."))))
    async with SessionLocal() as session:
        row = await session.get(Setting, "salary_target_uah")
        if row:
            row.value = value
        else:
            session.add(Setting(key="salary_target_uah", value=value))
        await session.commit()
    await message.answer(f"Орієнтир зарплати: {value} ₴.", reply_markup=main_kb())


async def prompt_salary(message: Message, state: FSMContext) -> None:
    async with SessionLocal() as session:
        row = await session.get(Setting, "salary_target_uah")
    await state.set_state(Form.salary)
    await message.answer(
        f"Поточний орієнтир: {row.value if row else '40000'} ₴.\nНапиши нове число, наприклад 40000.",
        reply_markup=main_kb(),
    )


async def save_income(message: Message, raw: str, note: str | None = None) -> None:
    amount = Decimal(raw.replace(" ", "").replace("₴", "").replace(",", "."))
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
                    "description": note or "Готівкова зарплата (ручний ввід)",
                    "mcc": "",
                    "amount_uah": amount,
                    "bank_category": "Зарахування",
                }
            ],
        )
    await message.answer(
        f"Записав надходження {amount} ₴ ({result['inserted']} нових).",
        reply_markup=main_kb(),
    )


async def prompt_income(message: Message, state: FSMContext) -> None:
    await state.set_state(Form.income)
    await message.answer("Напиши суму готівки, наприклад 12000.", reply_markup=main_kb())


async def save_limit(message: Message, cat: str, amt: str) -> None:
    key = f"limit_{cat}"
    async with SessionLocal() as session:
        row = await session.get(Setting, key)
        if row:
            row.value = amt
        else:
            session.add(Setting(key=key, value=amt))
        await session.commit()
    await message.answer(f"Ліміт {category_label(cat)}: {amt} ₴", reply_markup=main_kb())


async def prompt_limits(message: Message) -> None:
    await message.answer("Обери категорію:", reply_markup=kb_limit_cats())


@router.message(Command("salary"))
async def cmd_salary(message: Message, command: CommandObject, state: FSMContext):
    if not command.args:
        await prompt_salary(message, state)
        return
    try:
        await save_salary(message, command.args)
    except Exception:
        await message.answer("Потрібне число, наприклад 40000", reply_markup=main_kb())


@router.message(Command("income"))
async def cmd_income(message: Message, command: CommandObject, state: FSMContext):
    parts = (command.args or "").split(maxsplit=1)
    if not parts or not parts[0]:
        await prompt_income(message, state)
        return
    try:
        await save_income(message, parts[0], parts[1] if len(parts) > 1 else None)
    except Exception:
        await message.answer("Потрібне число, наприклад 12000", reply_markup=main_kb())


@router.message(Command("limit"))
async def cmd_limit(message: Message, command: CommandObject):
    parts = (command.args or "").split()
    if len(parts) != 2:
        await prompt_limits(message)
        return
    cat, amt = parts[0].upper(), parts[1]
    if cat not in CATEGORIES:
        await prompt_limits(message)
        return
    try:
        Decimal(amt.replace(",", "."))
    except Exception:
        await message.answer("Сума має бути числом", reply_markup=main_kb())
        return
    await save_limit(message, cat, amt)


@router.message(F.text == BTN_STATUS)
async def btn_status(message: Message, state: FSMContext):
    await state.clear()
    await cmd_status(message)


@router.message(F.text == BTN_DEBT)
async def btn_debt(message: Message, state: FSMContext):
    await state.clear()
    await cmd_debt(message)


@router.message(F.text == BTN_WEEK)
async def btn_week(message: Message, state: FSMContext):
    await state.clear()
    await cmd_week(message)


@router.message(F.text == BTN_SYNC)
async def btn_sync(message: Message, state: FSMContext):
    await state.clear()
    await cmd_sync(message)


@router.message(F.text == BTN_LIMITS)
async def btn_limits(message: Message, state: FSMContext):
    await state.clear()
    await prompt_limits(message)


@router.message(F.text == BTN_SALARY)
async def btn_salary(message: Message, state: FSMContext):
    await prompt_salary(message, state)


@router.message(F.text == BTN_INCOME)
async def btn_income(message: Message, state: FSMContext):
    await prompt_income(message, state)


@router.message(Form.limit_amount, F.text)
async def on_limit_amount(message: Message, state: FSMContext):
    raw = (message.text or "").replace(" ", "").replace("₴", "").replace(",", ".")
    try:
        amt = str(int(Decimal(raw)))
    except Exception:
        await message.answer("Потрібне число, наприклад 6000", reply_markup=main_kb())
        return
    data = await state.get_data()
    cat = data.get("cat")
    await state.clear()
    if not cat or cat not in CATEGORIES:
        await prompt_limits(message)
        return
    await save_limit(message, cat, amt)


@router.message(Form.salary, F.text)
async def on_salary_amount(message: Message, state: FSMContext):
    try:
        await save_salary(message, message.text or "")
        await state.clear()
    except Exception:
        await message.answer("Потрібне число, наприклад 40000", reply_markup=main_kb())


@router.message(Form.income, F.text)
async def on_income_amount(message: Message, state: FSMContext):
    try:
        await save_income(message, message.text or "")
        await state.clear()
    except Exception:
        await message.answer("Потрібне число, наприклад 12000", reply_markup=main_kb())


@router.message(Command("sync"))
async def cmd_sync(message: Message):
    if sync_busy():
        sec = sync_running_seconds()
        await message.answer(
            f"Уже тягну Monobank ({sec // 60} хв {sec % 60} с). "
            "Не тисни синк ще раз — напишу, коли закінчу або впаде.",
            reply_markup=main_kb(),
        )
        return
    await message.answer(
        "Оновлюю ліміти карток. Виписки чорної/білої — з паузою Моно ~1 хв між запитами.",
        reply_markup=main_kb(),
    )

    async def progress(text: str):
        try:
            await message.answer(text)
        except Exception:
            log.exception("sync progress failed")

    try:
        result = await sync_statements(days=31, progress=progress, use_llm=False)
        async with SessionLocal() as session:
            await notify_new(message.bot, result["alerts"], session)
        await message.answer(
            f"Готово: нових {result['inserted']}, уже були {result['skipped']}.",
            reply_markup=main_kb(),
        )
    except MonoError as exc:
        await message.answer(str(exc), reply_markup=main_kb())
    except Exception as exc:
        log.exception("sync failed")
        await message.answer(f"Синк упав: {exc}", reply_markup=main_kb())


@router.message(F.document)
async def on_document(message: Message, bot: Bot):
    doc = message.document
    name = (doc.file_name or "file.xlsx").lower()
    if not name.endswith((".xlsx", ".xls", ".csv")):
        await message.answer("Потрібен Excel/CSV виписки.", reply_markup=main_kb())
        return
    await message.answer("Читаю виписку…", reply_markup=main_kb())
    import tempfile

    dest = Path(tempfile.gettempdir()) / (doc.file_name or "statement.xlsx")
    await bot.download(doc, destination=dest)
    async with SessionLocal() as session:
        result = await import_path(session, dest)
        await notify_new(bot, result.get("alerts") or [], session)
    dest.unlink(missing_ok=True)
    await message.answer(
        f"Імпорт ({result.get('kind')}): нових {result['inserted']}, дублі {result['skipped']}.",
        reply_markup=main_kb(),
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
        await query.message.answer(f"Записав як {category_label(cat)}.", reply_markup=main_kb())


@router.callback_query(F.data.startswith("lim:"))
async def on_lim_cat(query: CallbackQuery, state: FSMContext):
    cat = (query.data or "").split(":", 1)[1]
    if cat not in CATEGORIES:
        await query.answer("Немає такої категорії", show_alert=True)
        return
    await state.set_state(Form.limit_amount)
    await state.update_data(cat=cat)
    await query.answer()
    if query.message:
        await query.message.answer(
            f"Ліміт для «{category_label(cat)}». Напиши суму в ₴, наприклад 6000.",
            reply_markup=main_kb(),
        )


@router.message()
async def on_other(message: Message):
    text = (message.text or "").strip()
    log.info("unhandled telegram text=%r chat=%s", text[:80], message.chat.id if message.chat else None)
    await message.answer("Обери дію кнопкою внизу.", reply_markup=main_kb())


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
