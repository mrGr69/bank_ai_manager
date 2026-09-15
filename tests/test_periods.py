from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.ledger import fmt_range, week_bounds

KYIV = ZoneInfo("Europe/Kyiv")


def test_week_starts_monday():
    wed = datetime(2026, 9, 16, 15, 0, tzinfo=KYIV)
    start, end = week_bounds(wed)
    assert start.weekday() == 0
    assert start.day == 14
    assert "14–16 вересня" in fmt_range(start, end)
