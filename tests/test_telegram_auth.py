from app.bot.handlers import allowed
from app.config import Settings, parse_telegram_user_id


def test_parse_strips_quotes_and_spaces():
    assert parse_telegram_user_id('  "123456789"  ') == 123456789
    assert parse_telegram_user_id("'123'") == 123
    assert parse_telegram_user_id("") is None
    assert parse_telegram_user_id(None) is None


def test_settings_coerces_quoted_user_id():
    s = Settings(telegram_user_id='"987654321"')
    assert s.telegram_user_id == 987654321


def test_allowed_compares_as_int(monkeypatch):
    from app.bot import handlers

    monkeypatch.setattr(handlers.settings, "telegram_user_id", 111)
    assert allowed(111) is True
    assert allowed("111") is True
    assert allowed(222) is False
