from __future__ import annotations

import json
from decimal import Decimal

import httpx

from app.classify.rules import Classified
from app.config import settings


SYSTEM = """Ти фінансовий класифікатор особистих витрат українською.
Поверни СТРОГО JSON без markdown:
{"category":"...","confidence":0.0,"clarification_needed":true,
 "clarification_title":"...","clarification_options":[{"label":"...","cat":"..."}],
 "coach_comment":"..."}
category лише з цього списку:
INCOME_SALARY, HOUSING_FIXED, GROCERIES_HOME, DINING_LEISURE, DATING_ROMANCE,
TRANSIT_URBAN, TRANSIT_TAXI, INTERCITY_TRAVEL, SUBSCRIPTIONS_WORK, HEALTH_CARE,
CLOTHING_HOUSEHOLD, TOBACCO_RELAX, P2P_TRANSFER, CASH_MOVEMENT, ONE_OFF,
FAMILY_SUPPORT, DEBT_INTEREST, UNCATEGORIZED_SUSPICIOUS
coach_comment до 140 символів, тон партнерський, без моралі.
clarification_needed=true якщо неясно що це, або великий ресторанний чек, або P2P.
"""


async def classify_llm(description: str, mcc: str, amount: Decimal, bank_category: str = "") -> Classified | None:
    if not settings.openai_api_key:
        return None
    payload = {
        "model": settings.openai_model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Опис: {description}\nMCC: {mcc}\nСума: {amount} UAH\n"
                    f"Банківська категорія: {bank_category or '—'}"
                ),
            },
        ],
    }
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    url = settings.openai_base_url.rstrip("/") + "/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
    except Exception:
        return None
    return Classified(
        category=data.get("category") or "UNCATEGORIZED_SUSPICIOUS",
        confidence=float(data.get("confidence") or 0.5),
        clarification_needed=bool(data.get("clarification_needed")),
        clarification_title=data.get("clarification_title"),
        clarification_options=data.get("clarification_options") or [],
        coach_comment=str(data.get("coach_comment") or "")[:140],
    )
