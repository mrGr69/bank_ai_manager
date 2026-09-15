from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.importers.mono import parse_mono_statement
from app.importers.privat import parse_privat_statement, privat_account_code
from app.services.ingest import get_account, ingest_items


def detect_kind(path: Path) -> str:
    name = path.name.lower()
    if name.startswith("report_"):
        return "mono"
    return "unknown"


async def import_path(session: AsyncSession, path: Path, kind: str | None = None) -> dict:
    kind = kind or detect_kind(path)
    from app.importers.common import iter_xlsx_rows

    first = []
    for i, row in enumerate(iter_xlsx_rows(path)):
        first.append(row)
        if i >= 5:
            break
    blob = " ".join(str(c) for r in first for c in (r or []) if c)
    if "Історія операцій" in blob or "Категорія" in blob:
        kind = "privat"
    elif "Рух коштів" in blob or "MCC" in blob or "Кредитний" in blob or "Заборгованість" in blob:
        kind = "mono"

    if kind == "privat":
        parsed = parse_privat_statement(path)
        grouped: dict[str, list] = {}
        for item in parsed["items"]:
            code = privat_account_code(item.get("last4") or "")
            grouped.setdefault(code, []).append(item)
        total = {"inserted": 0, "skipped": 0, "alerts": [], "kind": "privat"}
        for code, items in grouped.items():
            result = await ingest_items(
                session, bank="privat", account_code=code, source="privat_file", items=items
            )
            total["inserted"] += result["inserted"]
            total["skipped"] += result["skipped"]
            total["alerts"].extend(result["alerts"])
        # Privat credit card last balance as debt if negative
        credit_items = grouped.get("credit") or []
        if credit_items:
            last = max(credit_items, key=lambda x: x["occurred_at"])
            acc = await get_account(session, "privat", "credit")
            bal = last.get("balance_after")
            acc.last_balance_uah = bal
            if bal is not None and bal < 0:
                acc.last_debt_uah = -bal
            acc.last_synced_at = datetime.now(timezone.utc)
            await session.commit()
        return total

    parsed = parse_mono_statement(path)
    meta = parsed["meta"]
    limit = meta.get("credit_limit")
    if limit is not None and Decimal(limit) == 0:
        code = "white"
    else:
        code = "black"
    result = await ingest_items(
        session, bank="mono", account_code=code, source="mono_file", items=parsed["items"]
    )
    acc = await get_account(session, "mono", code)
    if meta.get("credit_limit") is not None:
        acc.credit_limit_uah = meta["credit_limit"]
    if meta.get("debt") is not None:
        acc.last_debt_uah = meta["debt"]
    acc.last_synced_at = datetime.now(timezone.utc)
    await session.commit()
    result["kind"] = "mono"
    result["account"] = code
    return result
