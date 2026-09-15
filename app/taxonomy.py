"""Closed category set used in reports, alerts and Telegram buttons."""

CATEGORIES = {
    "INCOME_SALARY": "Зарплата / премія",
    "HOUSING_FIXED": "Оренда + комуналка",
    "GROCERIES_HOME": "Продукти додому",
    "DINING_LEISURE": "Кафе, бари, доставка",
    "DATING_ROMANCE": "Дейтинг / побачення",
    "TRANSIT_URBAN": "Міський транспорт / самокат",
    "TRANSIT_TAXI": "Таксі",
    "INTERCITY_TRAVEL": "Міжмісто / готель",
    "SUBSCRIPTIONS_WORK": "Підписки і софт",
    "HEALTH_CARE": "Здоров'я",
    "CLOTHING_HOUSEHOLD": "Одяг / побут",
    "TOBACCO_RELAX": "Тютюн",
    "P2P_TRANSFER": "P2P без мітки",
    "CASH_MOVEMENT": "Готівка",
    "ONE_OFF": "Разове (поза побутом)",
    "FAMILY_SUPPORT": "Родина",
    "DEBT_INTEREST": "Відсотки за кредитом",
    "UNCATEGORIZED_SUSPICIOUS": "Неясно",
}

ESSENTIAL = {
    "INCOME_SALARY",
    "HOUSING_FIXED",
    "GROCERIES_HOME",
    "TRANSIT_URBAN",
    "HEALTH_CARE",
    "SUBSCRIPTIONS_WORK",
}

LEAK_CATEGORIES = {
    "DINING_LEISURE",
    "TRANSIT_TAXI",
    "DATING_ROMANCE",
}

DEFAULT_LIMITS = {
    "DINING_LEISURE": 6000,
    "TRANSIT_TAXI": 2000,
    "DATING_ROMANCE": 800,
    "TOBACCO_RELAX": 1500,
    "GROCERIES_HOME": 8000,
}

DEFAULT_SETTINGS = {
    "salary_target_uah": "40000",
    "housing_typical_uah": "12500",
    "dining_large_uah": "1200",
    "taxi_large_uah": "500",
    "p2p_clarify_uah": "200",
    "weekly_report_hour": "20",
    "weekly_report_dow": "sun",
}


def all_category_options() -> list[dict]:
    return [
        {"label": label[:40], "cat": code}
        for code, label in CATEGORIES.items()
        if code != "UNCATEGORIZED_SUSPICIOUS"
    ]
