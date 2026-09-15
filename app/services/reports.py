from __future__ import annotations

from io import BytesIO
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.ledger import category_label, debt_snapshot, fmt_money, month_summary
from app.taxonomy import LEAK_CATEGORIES

KYIV = ZoneInfo(settings.tz)


async def weekly_text(session: AsyncSession) -> str:
    s = await month_summary(session)
    lines = [
        "📊 Тижневий розбір (місяць до сьогодні)",
        f"Орієнтир доходу: {fmt_money(s['salary_target'])}",
        f"Надходження (зовнішні): {fmt_money(s['income'])}",
        f"Витрати (зовнішні): {fmt_money(s['spent'])}",
        f"Залишок відносно орієнтиру: {fmt_money(s['free'])}",
        "",
        "Витоки:",
    ]
    for cat in LEAK_CATEGORIES:
        lines.append(f"• {category_label(cat)}: {fmt_money(s['leaks'][cat])}")
    lines.append("")
    lines.append("Категорії:")
    cats = sorted(s["by_cat"].items(), key=lambda kv: kv[1]["sum"])
    for cat, data in cats[:12]:
        lines.append(f"• {category_label(cat)}: {fmt_money(data['sum'])} ({data['n']})")
    debts = await debt_snapshot(session)
    if debts:
        lines.append("")
        lines.append("Борги:")
        for d in debts:
            lines.append(f"• {d['title']}: {fmt_money(d['debt'])} з {fmt_money(d['limit'])}")
            if d["limit"] and d["debt"] and d["limit"] > 0:
                pct = float(d["debt"] / d["limit"] * 100)
                if pct >= 80:
                    lines.append("  → ліміт майже вибраний. Спочатку зарплата на борг, не в кафе.")
    if abs(s["leaks"]["DINING_LEISURE"]) > 0:
        lines.append("")
        lines.append("На наступний тиждень: кафе/доставка — стеля. Таксі — лише якщо реально треба.")
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
