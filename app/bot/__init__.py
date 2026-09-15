from aiogram import Bot
from app.bot.handlers import dp
from app.config import settings

bot: Bot | None = None


def get_bot() -> Bot:
    global bot
    if bot is None:
        if not settings.telegram_bot_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN порожній")
        bot = Bot(token=settings.telegram_bot_token)
    return bot


async def start_polling() -> None:
    await dp.start_polling(get_bot(), allowed_updates=dp.resolve_used_update_types())
