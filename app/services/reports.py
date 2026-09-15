from __future__ import annotations

from datetime import datetime, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.ledger import (
    MONTHS_NOM,
    category_label,
    debt_snapshot,
    fmt_money,
    fmt_range,
    month_summary,
    period_summary,
    week_bounds,
)
from app.taxonomy import LEAK_CATEGORIES

KYIV = ZoneInfo(settings.tz)


def _one_action(s: dict, *, for_week: bool) -> str:
    cafe = abs(s["leaks"]["DINING_LEISURE"])
    taxi = abs(s["leaks"]["TRANSIT_TAXI"])
    if cafe >= taxi and cafe > 0:
        if for_week:
            return "На найближчі дні: кафе/доставка — стеля. Таксі лише якщо реально треба."
        return "Якщо так піде далі — ріж кафе і доставку, не «все підряд»."
    if taxi > 0:
        return "Таксі набігає. Місто/самокат, якщо не дощ і валізи."
    return "Дір по кафе/таксі майже немає — тримай так."


async def month_text(session: AsyncSession) -> str:
    now = datetime.now(KYIV)
    s = await month_summary(session)
    start, end = s["start"], s["end"]
    days_left = max(0, (end.date() - now.date()).days)
    debts = await debt_snapshot(session)
    lines = [
        f"📅 Місяць · {MONTHS_NOM[start.month]} {start.year}",
        f"Період: {fmt_range(start, now + timedelta(seconds=1))} (з 1 числа до сьогодні).",
        "Це не тиждень. Тиждень — окрема кнопка.",
        "",
        "Факт з карток:",
        f"Зайшло: {fmt_money(s['income'])}",
        f"Пішло: {fmt_money(s['spent'])}",
        f"План (орієнтир, не факт): {fmt_money(s['salary_target'])}",
        "",
        "Діри:",
        f"• Кафе / бари / доставка: {fmt_money(s['leaks']['DINING_LEISURE'])}",
        f"• Таксі: {fmt_money(s['leaks']['TRANSIT_TAXI'])}",
        f"• Дейтинг: {fmt_money(s['leaks']['DATING_ROMANCE'])}",
    ]
    unclear = s["by_cat"].get("UNCATEGORIZED_SUSPICIOUS")
    if unclear and unclear["n"]:
        lines.append(f"• Неясно: {fmt_money(unclear['sum'])} ({unclear['n']} шт.) — натисни кнопки під тими чеками")
    if debts:
        lines.append("")
        lines.append("Борг зараз:")
        for d in debts:
            lines.append(f"• {d['title']}: {fmt_money(d['debt'])} з {fmt_money(d['limit'])}")
    if days_left:
        lines.append("")
        lines.append(f"До кінця місяця ще {days_left} дн.")
    lines.append("")
    lines.append(_one_action(s, for_week=False))
    return "\n".join(lines)


async def weekly_text(session: AsyncSession) -> str:
    now = datetime.now(KYIV)
    start, end = week_bounds(now)
    s = await period_summary(session, start, end)
    lines = [
        f"📆 Тиждень · {fmt_range(start, end)}",
        "З понеділка до сьогодні. Це не весь місяць.",
        "",
        f"Зайшло: {fmt_money(s['income'])}",
        f"Пішло: {fmt_money(s['spent'])}",
        "",
        "За цей тиждень:",
    ]
    for cat in LEAK_CATEGORIES:
        lines.append(f"• {category_label(cat)}: {fmt_money(s['leaks'][cat])}")
    cats = sorted(s["by_cat"].items(), key=lambda kv: kv[1]["sum"])
    spent_cats = [(c, d) for c, d in cats if d["sum"] < 0][:6]
    if spent_cats:
        lines.append("")
        lines.append("Топ витрат:")
        for cat, data in spent_cats:
            lines.append(f"• {category_label(cat)}: {fmt_money(data['sum'])} ({data['n']})")
    lines.append("")
    lines.append(_one_action(s, for_week=True))
    return "\n".join(lines)


async def debt_chart_png(session: AsyncSession) -> bytes | None:
    debts = await debt_snapshot(session)
    debts = [d for d in debts if d["debt"] is not None]
    if not debts:
        return None
    labels = [d["title"][:22] for d in debts]
    values = [float(d["debt"] or 0) for d in debts]
    limits = [float(d["limit"] or 0) for d in debts]
    fig, ax = plt.subplots(figsize=(7, 4), dpi=140)
    ax.bar(labels, limits, color="#d9d9d9", label="Ліміт")
    ax.bar(labels, values, color="#c0392b", label="Борг")
    ax.set_ylabel("₴")
    ax.set_title("Кредитні ліміти vs борг")
    ax.legend()
    fig.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
