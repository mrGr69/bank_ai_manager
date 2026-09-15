"""Sentinel — особистий аудитор витрат у Telegram.

## Що вміє v1
- Тягне Monobank (API + webhook).
- Приймає Excel виписки Привату файлом у чат.
- Ховає внутрішні перекази між своїми картками.
- Алерти: великий чек кафе/таксі, пробитий ліміт категорії, «не зрозумів».
- Неділя 20:00 Київ — тижневий розбір + графік боргів.
- Зарплата / ліміти міняються командами, без деплою.

## Railway
1. Репозиторій на GitHub (виписки `.xls/.xlsx` у `.gitignore` — не комітити).
2. New project на https://railway.com → Postgres plugin → сервіс з цього Dockerfile.
3. Variables:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_USER_ID`
   - `MONOBANK_TOKEN`
   - `PUBLIC_URL` = `https://<твій-сервіс>.up.railway.app`
   - `OPENAI_API_KEY` (необов'язково)
   Railway сам додає `DATABASE_URL`.
4. Після деплою `/health` має відповісти `{"ok":true}`.
5. Напиши боту `/start`, потім `/sync`. Історію Привату кинь файлом у чат.
   Локально історію з кореня: `python -m app.cli import-history`

## Локально
```
docker compose up -d
copy .env.example .env
python -m venv .venv
.venv\\Scripts\\pip install -r requirements.txt
python -m app.cli seed
python -m app.cli import-history
uvicorn app.main:app --reload
```
Без `PUBLIC_URL` бот іде в long polling.

## Команди
- `/status` `/debt` `/week` `/sync`
- `/salary 40000`
- `/income 12000` — готівкова частина зарплати
- `/limit DINING_LEISURE 6000`
"""
