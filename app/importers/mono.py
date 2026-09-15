from __future__ import annotations

from pathlib import Path

from app.importers.common import parse_dt, parse_money, iter_xlsx_rows


def parse_mono_statement(path: Path, account_hint: str | None = None) -> dict:
    rows = list(iter_xlsx_rows(path))
    meta: dict = {"account_hint": account_hint or "", "credit_limit": None, "debt": None, "period": ""}
    items: list[dict] = []
    header_idx = None
    for i, row in enumerate(rows):
        cell = str(row[0] or "")
        if "Кредитний ліміт" in cell or "Кредитний ліміт" in cell or "Кредитний ліміт" in cell:
            meta["credit_limit"] = _extract_money(cell)
        if cell.startswith("Заборгованість"):
            meta["debt"] = _extract_money(cell)
        if cell.startswith("Період:"):
            meta["period"] = cell
        if cell.startswith("Інформація по картці"):
            meta["cards"] = cell
        if cell.startswith("Дата") and row[1] and "MCC" in str(row[2] or ""):
            header_idx = i
            break
    if header_idx is None:
        return {"meta": meta, "items": items}
    for row in rows[header_idx + 1 :]:
        if not row or not row[0]:
            continue
        occurred = parse_dt(row[0])
        if not occurred:
            continue
        items.append(
            {
                "occurred_at": occurred,
                "description": str(row[1] or "").strip(),
                "mcc": str(row[2] or "").strip(),
                "amount_uah": parse_money(row[3]) or 0,
                "original_amount": parse_money(row[4]),
                "original_currency": str(row[5] or "UAH"),
                "fee_uah": parse_money(row[7]) or 0,
                "cashback_uah": parse_money(row[8]) or 0,
                "balance_after": parse_money(row[9]),
                "bank_category": "",
                "card_mask": "",
            }
        )
    return {"meta": meta, "items": items}


def _extract_money(cell: str):
    from app.importers.common import parse_money

    # "Кредитний ліміт (станом на 13.09.2026): 25 000.00 UAH"
    if ":" in cell:
        return parse_money(cell.split(":")[-1])
    return None
