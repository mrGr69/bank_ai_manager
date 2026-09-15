from __future__ import annotations

from pathlib import Path

from app.importers.common import card_last4, iter_xlsx_rows, parse_dt, parse_money


def parse_privat_statement(path: Path) -> dict:
    rows = list(iter_xlsx_rows(path))
    items: list[dict] = []
    header_idx = None
    for i, row in enumerate(rows):
        if row and str(row[0] or "").strip() == "Дата":
            header_idx = i
            break
    if header_idx is None:
        return {"meta": {}, "items": items}
    for row in rows[header_idx + 1 :]:
        if not row or not row[0]:
            continue
        occurred = parse_dt(row[0])
        if not occurred:
            continue
        items.append(
            {
                "occurred_at": occurred,
                "bank_category": str(row[1] or "").strip(),
                "card_mask": str(row[2] or "").strip(),
                "last4": card_last4(row[2]),
                "description": str(row[3] or "").strip(),
                "amount_uah": parse_money(row[4]) or 0,
                "original_amount": parse_money(row[6]),
                "original_currency": str(row[7] or "UAH"),
                "balance_after": parse_money(row[8]),
                "mcc": "",
                "fee_uah": 0,
                "cashback_uah": 0,
            }
        )
    return {"meta": {}, "items": items}


def privat_account_code(last4: str) -> str:
    if last4 == "6993":
        return "salary"
    if last4 == "4038":
        return "credit"
    if last4 == "7977":
        return "other"
    return "other"
