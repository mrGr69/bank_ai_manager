from app.bot.handlers import allowed
from app.bot.updates import remember_update
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


def test_remember_update_drops_duplicates():
    uid = 378882588
    assert remember_update(uid) is True
    assert remember_update(uid) is False
    assert remember_update(uid + 1) is True


def test_limit_callback_data_fits_telegram():
    from app.bot.handlers import kb_limit_cats

    kb = kb_limit_cats()
    assert kb.inline_keyboard
    for row in kb.inline_keyboard:
        for btn in row:
            assert btn.callback_data and len(btn.callback_data.encode()) <= 64
