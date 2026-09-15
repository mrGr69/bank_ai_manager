from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass
class Classified:
    category: str
    confidence: float
    is_internal: bool = False
    exclude_from_budget: bool = False
    is_essential: bool = False
    is_anomaly: bool = False
    budget_impact: str = "LOW"
    clarification_needed: bool = False
    clarification_title: str | None = None
    clarification_options: list[dict] | None = None
    coach_comment: str = ""


SEED_RULES: list[dict] = [
    {"pattern": "блюберд", "category": "INCOME_SALARY", "is_internal": False, "is_essential": True, "exclude_from_budget": False, "notes": "зарплата ТОВ"},
    {"pattern": "zarobitna plata", "category": "INCOME_SALARY", "is_internal": False, "is_essential": True, "exclude_from_budget": False, "notes": ""},
    {"pattern": "premiia", "category": "INCOME_SALARY", "is_internal": False, "is_essential": True, "exclude_from_budget": False, "notes": "премія, входить у орієнтир 40к"},
    {"pattern": "станіслава", "category": "HOUSING_FIXED", "is_internal": False, "is_essential": True, "exclude_from_budget": False, "notes": "оренда+комуналка"},
    {"pattern": "portmone", "category": "HOUSING_FIXED", "is_internal": False, "is_essential": True, "exclude_from_budget": False, "notes": ""},
    {"pattern": "volia", "category": "HOUSING_FIXED", "is_internal": False, "is_essential": True, "exclude_from_budget": False, "notes": ""},
    {"pattern": "воля", "category": "HOUSING_FIXED", "is_internal": False, "is_essential": True, "exclude_from_budget": False, "notes": ""},
    {"pattern": "сільпо", "category": "GROCERIES_HOME", "is_internal": False, "is_essential": True, "exclude_from_budget": False, "notes": ""},
    {"pattern": "фора", "category": "GROCERIES_HOME", "is_internal": False, "is_essential": True, "exclude_from_budget": False, "notes": ""},
    {"pattern": "атб", "category": "GROCERIES_HOME", "is_internal": False, "is_essential": True, "exclude_from_budget": False, "notes": ""},
    {"pattern": "делікат", "category": "GROCERIES_HOME", "is_internal": False, "is_essential": True, "exclude_from_budget": False, "notes": ""},
    {"pattern": "деликат", "category": "GROCERIES_HOME", "is_internal": False, "is_essential": True, "exclude_from_budget": False, "notes": ""},
    {"pattern": "зелений слон", "category": "GROCERIES_HOME", "is_internal": False, "is_essential": True, "exclude_from_budget": False, "notes": ""},
    {"pattern": "zeleniy slon", "category": "GROCERIES_HOME", "is_internal": False, "is_essential": True, "exclude_from_budget": False, "notes": ""},
    {"pattern": "dim pyva", "category": "DINING_LEISURE", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": "пиво, не кошик"},
    {"pattern": "manufaktura", "category": "DINING_LEISURE", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "liubchyk", "category": "DINING_LEISURE", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "1818kyiv", "category": "DINING_LEISURE", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "чорноморка", "category": "DINING_LEISURE", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "пузата хата", "category": "DINING_LEISURE", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "mcdonald", "category": "DINING_LEISURE", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "kfc", "category": "DINING_LEISURE", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "glovo", "category": "DINING_LEISURE", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "bolt food", "category": "DINING_LEISURE", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "zerno pizza", "category": "DINING_LEISURE", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "street house", "category": "DINING_LEISURE", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "білий налив", "category": "DINING_LEISURE", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "bilyi nalyv", "category": "DINING_LEISURE", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "molti", "category": "DINING_LEISURE", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "aroma kava", "category": "DINING_LEISURE", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "рис та локшина", "category": "DINING_LEISURE", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "ristalokshina", "category": "DINING_LEISURE", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "spletni", "category": "DINING_LEISURE", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "uklon", "category": "TRANSIT_TAXI", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "bolt", "category": "TRANSIT_TAXI", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "київпастранс", "category": "TRANSIT_URBAN", "is_internal": False, "is_essential": True, "exclude_from_budget": False, "notes": ""},
    {"pattern": "громадський транспорт", "category": "TRANSIT_URBAN", "is_internal": False, "is_essential": True, "exclude_from_budget": False, "notes": ""},
    {"pattern": "київське метро", "category": "TRANSIT_URBAN", "is_internal": False, "is_essential": True, "exclude_from_budget": False, "notes": ""},
    {"pattern": "kyivtr", "category": "TRANSIT_URBAN", "is_internal": False, "is_essential": True, "exclude_from_budget": False, "notes": ""},
    {"pattern": "kyiv metro", "category": "TRANSIT_URBAN", "is_internal": False, "is_essential": True, "exclude_from_budget": False, "notes": ""},
    {"pattern": "jet.ua", "category": "TRANSIT_URBAN", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": "самокат"},
    {"pattern": "bikenow", "category": "TRANSIT_URBAN", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "ukrzaliznytsia", "category": "INTERCITY_TRAVEL", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "укрзалізниця", "category": "INTERCITY_TRAVEL", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "blablacar", "category": "INTERCITY_TRAVEL", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "guest house", "category": "INTERCITY_TRAVEL", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "spotify", "category": "SUBSCRIPTIONS_WORK", "is_internal": False, "is_essential": True, "exclude_from_budget": False, "notes": ""},
    {"pattern": "cursor", "category": "SUBSCRIPTIONS_WORK", "is_internal": False, "is_essential": True, "exclude_from_budget": False, "notes": ""},
    {"pattern": "telegram", "category": "SUBSCRIPTIONS_WORK", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "табакерка", "category": "TOBACCO_RELAX", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "tabakerka", "category": "TOBACCO_RELAX", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "фортуна", "category": "TOBACCO_RELAX", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "аврора", "category": "CLOTHING_HOUSEHOLD", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "humana", "category": "CLOTHING_HOUSEHOLD", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "антошка", "category": "CLOTHING_HOUSEHOLD", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "аптека", "category": "HEALTH_CARE", "is_internal": False, "is_essential": True, "exclude_from_budget": False, "notes": ""},
    {"pattern": "подорожник", "category": "HEALTH_CARE", "is_internal": False, "is_essential": True, "exclude_from_budget": False, "notes": ""},
    {"pattern": "чну", "category": "ONE_OFF", "is_internal": False, "is_essential": False, "exclude_from_budget": True, "notes": "навчання, поза побутом"},
    {"pattern": "зачешигрива в.", "category": "FAMILY_SUPPORT", "is_internal": False, "is_essential": False, "exclude_from_budget": True, "notes": "родина, покрила навчання"},
    {"pattern": "зі своєї картки", "category": "P2P_TRANSFER", "is_internal": True, "is_essential": False, "exclude_from_budget": True, "notes": ""},
    {"pattern": "на картку", "category": "P2P_TRANSFER", "is_internal": True, "is_essential": False, "exclude_from_budget": True, "notes": "перекид на моно/свою"},
    {"pattern": "з чорної картки", "category": "P2P_TRANSFER", "is_internal": True, "is_essential": False, "exclude_from_budget": True, "notes": ""},
    {"pattern": "з білої картки", "category": "P2P_TRANSFER", "is_internal": True, "is_essential": False, "exclude_from_budget": True, "notes": ""},
    {"pattern": "monodirect", "category": "P2P_TRANSFER", "is_internal": True, "is_essential": False, "exclude_from_budget": True, "notes": ""},
    {"pattern": "скасування.", "category": "P2P_TRANSFER", "is_internal": True, "is_essential": False, "exclude_from_budget": True, "notes": "холд, нетто 0"},
    {"pattern": "кредитного ліміту", "category": "DEBT_INTEREST", "is_internal": False, "is_essential": False, "exclude_from_budget": False, "notes": ""},
    {"pattern": "зняття готівки", "category": "CASH_MOVEMENT", "is_internal": False, "is_essential": False, "exclude_from_budget": True, "notes": "велика каса премії — не побут"},
    {"pattern": "каса м ", "category": "CASH_MOVEMENT", "is_internal": False, "is_essential": False, "exclude_from_budget": True, "notes": ""},
]


MCC_MAP = {
    "5411": "GROCERIES_HOME",
    "5499": "GROCERIES_HOME",
    "5441": "GROCERIES_HOME",
    "5812": "DINING_LEISURE",
    "5813": "DINING_LEISURE",
    "5814": "DINING_LEISURE",
    "5811": "DINING_LEISURE",
    "4121": "TRANSIT_TAXI",
    "4111": "TRANSIT_URBAN",
    "4112": "INTERCITY_TRAVEL",
    "5815": "SUBSCRIPTIONS_WORK",
    "5816": "SUBSCRIPTIONS_WORK",
    "5817": "SUBSCRIPTIONS_WORK",
    "5734": "SUBSCRIPTIONS_WORK",
    "5993": "TOBACCO_RELAX",
    "5912": "HEALTH_CARE",
    "5541": "INTERCITY_TRAVEL",
    "4829": "P2P_TRANSFER",
    "6012": "P2P_TRANSFER",
    "4899": "HOUSING_FIXED",
    "4816": "HOUSING_FIXED",
    "7394": "TRANSIT_URBAN",
    "7999": "TRANSIT_URBAN",
}

INTERNAL_RE = re.compile(
    r"зі своєї картки|на свою картку|з чорної картки|з білої картки|"
    r"monodirect|скасування\.|від: zacheshyhryva|від: зачешигрива",
    re.I,
)

SALARY_SELF_RE = re.compile(r"від:\s*(zacheshyhryva|зачешигрива)", re.I)
GOOGLE_DATING_AMOUNT = Decimal("42.99")


def fingerprint(account_code: str, occurred_at: datetime, amount: Decimal, description: str, mcc: str = "") -> str:
    raw = f"{account_code}|{occurred_at.isoformat()}|{amount}|{description.strip().lower()}|{mcc}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _match_rule(description: str, extra_rules: list[dict] | None = None) -> dict | None:
    text = description.lower()
    rules = list(SEED_RULES)
    if extra_rules:
        rules = extra_rules + rules
    for rule in rules:
        if rule["pattern"].lower() in text:
            return rule
    return None


def classify_rules(
    *,
    description: str,
    mcc: str = "",
    amount: Decimal,
    bank_category: str = "",
    extra_rules: list[dict] | None = None,
    salary_target: Decimal = Decimal("40000"),
    dining_large: Decimal = Decimal("1200"),
    taxi_large: Decimal = Decimal("500"),
    p2p_clarify: Decimal = Decimal("200"),
) -> Classified:
    desc = description or ""
    amt = Decimal(amount)
    abs_amt = abs(amt)
    rule = _match_rule(desc, extra_rules)

    # Google 42.99 is dating; other Google is software.
    if re.search(r"\bgoogle\b", desc, re.I):
        if abs(abs_amt - GOOGLE_DATING_AMOUNT) <= Decimal("0.05"):
            rule = {
                "category": "DATING_ROMANCE",
                "is_internal": False,
                "is_essential": False,
                "exclude_from_budget": False,
            }
        elif not rule:
            rule = {
                "category": "SUBSCRIPTIONS_WORK",
                "is_internal": False,
                "is_essential": True,
                "exclude_from_budget": False,
            }

    is_internal = bool(rule and rule.get("is_internal"))
    if INTERNAL_RE.search(desc) and "блюберд" not in desc.lower() and "zarobitna" not in desc.lower():
        if SALARY_SELF_RE.search(desc) and amt > 0 and abs_amt >= Decimal("8000"):
            rule = {
                "category": "INCOME_SALARY",
                "is_internal": False,
                "is_essential": True,
                "exclude_from_budget": False,
            }
            is_internal = False
        else:
            is_internal = True

    if rule:
        category = rule["category"]
        confidence = 0.96
        is_essential = bool(rule.get("is_essential"))
        exclude = bool(rule.get("exclude_from_budget")) or is_internal
    elif mcc in MCC_MAP:
        category = MCC_MAP[mcc]
        confidence = 0.8
        from app.taxonomy import ESSENTIAL

        is_essential = category in ESSENTIAL
        exclude = is_internal
    elif bank_category:
        category = _bank_cat(bank_category)
        confidence = 0.7
        from app.taxonomy import ESSENTIAL

        is_essential = category in ESSENTIAL
        exclude = is_internal
    else:
        category = "UNCATEGORIZED_SUSPICIOUS"
        confidence = 0.35
        is_essential = False
        exclude = is_internal

    if is_internal:
        exclude = True

    clarification = False
    title = None
    options: list[dict] = []
    if category == "UNCATEGORIZED_SUSPICIOUS" and abs_amt >= Decimal("50"):
        clarification = True
        title = f"Не зрозумів «{desc[:40]}» на {abs_amt} ₴. Що це?"
        options = _generic_options()
    elif category == "P2P_TRANSFER" and not is_internal and abs_amt > p2p_clarify:
        clarification = True
        title = f"P2P {abs_amt} ₴ «{desc[:40]}». Куди пішли гроші?"
        options = [
            {"label": "🏠 Оренда / комуналка", "cat": "HOUSING_FIXED"},
            {"label": "🤝 Спільне / повернуть", "cat": "P2P_TRANSFER"},
            {"label": "🎁 Подарунок / родина", "cat": "FAMILY_SUPPORT"},
            {"label": "🍕 Кафе / відпочинок", "cat": "DINING_LEISURE"},
        ]
    elif category == "DINING_LEISURE" and abs_amt >= dining_large and amt < 0:
        clarification = True
        title = f"Чек {abs_amt} ₴ у «{desc[:32]}». Соло, сплит чи побачення?"
        options = [
            {"label": "🤝 Сплит, чекаю повернення", "cat": "DINING_LEISURE"},
            {"label": "🍸 Побачення", "cat": "DATING_ROMANCE"},
            {"label": "🍕 Мій відпочинок", "cat": "DINING_LEISURE"},
        ]

    impact = _impact(abs_amt, salary_target)
    anomaly = (category in {"DINING_LEISURE", "TRANSIT_TAXI"} and abs_amt >= dining_large) or clarification
    comment = _comment(category, desc, amt, abs_amt)

    return Classified(
        category=category,
        confidence=confidence,
        is_internal=is_internal,
        exclude_from_budget=exclude,
        is_essential=is_essential,
        is_anomaly=anomaly,
        budget_impact=impact,
        clarification_needed=clarification and not is_internal,
        clarification_title=title if clarification and not is_internal else None,
        clarification_options=options if clarification and not is_internal else [],
        coach_comment=comment,
    )


def _bank_cat(name: str) -> str:
    n = name.lower()
    mapping = [
        ("ресторан", "DINING_LEISURE"),
        ("кафе", "DINING_LEISURE"),
        ("супермаркет", "GROCERIES_HOME"),
        ("продукт", "GROCERIES_HOME"),
        ("таксі", "TRANSIT_TAXI"),
        ("транспорт", "TRANSIT_URBAN"),
        ("комунал", "HOUSING_FIXED"),
        ("одяг", "CLOTHING_HOUSEHOLD"),
        ("дім", "CLOTHING_HOUSEHOLD"),
        ("аптек", "HEALTH_CARE"),
        ("готел", "INTERCITY_TRAVEL"),
        ("азс", "INTERCITY_TRAVEL"),
        ("освіта", "ONE_OFF"),
        ("цифров", "SUBSCRIPTIONS_WORK"),
        ("кредит", "DEBT_INTEREST"),
        ("готівк", "CASH_MOVEMENT"),
        ("переказ", "P2P_TRANSFER"),
        ("зарахуван", "INCOME_SALARY"),
    ]
    for needle, cat in mapping:
        if needle in n:
            return cat
    return "UNCATEGORIZED_SUSPICIOUS"


def _impact(abs_amt: Decimal, salary: Decimal) -> str:
    if salary <= 0:
        salary = Decimal("40000")
    pct = abs_amt / salary
    if pct >= Decimal("0.25"):
        return "CRITICAL"
    if pct >= Decimal("0.10"):
        return "HIGH"
    if pct >= Decimal("0.03"):
        return "MEDIUM"
    return "LOW"


def _comment(category: str, desc: str, amt: Decimal, abs_amt: Decimal) -> str:
    if amt > 0 and category == "INCOME_SALARY":
        return f"Надходження {abs_amt:.0f} ₴. Це в орієнтир зарплати, не в «потрітив»."
    if category == "HOUSING_FIXED" and amt < 0:
        return f"Житло {abs_amt:.0f} ₴. Базовий платіж, головне не з кредитки."
    if category == "DINING_LEISURE" and abs_amt >= 1000:
        return f"{abs_amt:.0f} ₴ у кафе. Один вечір сильно б'є по вільному залишку."
    if category == "TRANSIT_TAXI":
        return f"Таксі {abs_amt:.0f} ₴. Якщо не дощ і валізи — це злив, не транспорт."
    if category == "DATING_ROMANCE":
        return "Дейтинг-списання. Дрібне, але рекурентне — місяцями набігає."
    if category == "TOBACCO_RELAX":
        return f"Тютюн {abs_amt:.0f} ₴. Фіксую як звичку, без моралі."
    if category == "DEBT_INTEREST":
        return "Це вже не грейс, а відсотки. Кредитка з'їдає зарплату."
    if category == "UNCATEGORIZED_SUSPICIOUS":
        return f"Не зрозумів «{desc[:28]}». Без мітки це діра в статистиці."
    if amt < 0:
        return f"{abs_amt:.0f} ₴ · {category}."
    return f"+{abs_amt:.0f} ₴"


def _generic_options() -> list[dict]:
    return [
        {"label": "🛒 Продукти / побут", "cat": "GROCERIES_HOME"},
        {"label": "🍕 Кафе / бар", "cat": "DINING_LEISURE"},
        {"label": "🚕 Таксі / дорога", "cat": "TRANSIT_TAXI"},
        {"label": "🤷 Разове, не побут", "cat": "ONE_OFF"},
    ]
