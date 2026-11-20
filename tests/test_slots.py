from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from bot.config import Settings
from bot.slots import parse_datetime_phrase, validate_calendar_day, working_hours


TZ = ZoneInfo("Asia/Chita")
TODAY = date(2025, 2, 25)


def test_slots_are_whole_hours_ten_to_seventeen() -> None:
    slots = working_hours(10, 18, 60)
    assert slots[0] == time(10, 0)
    assert slots[-1] == time(17, 0)
    assert time(15, 15) not in slots
    assert time(18, 0) not in slots
    assert time(9, 0) not in slots


def test_feb_29_2025_is_invalid() -> None:
    parsed, error = validate_calendar_day(2025, 2, 29)
    assert parsed is None
    assert error is not None
    assert "високосным" in error
    assert "28 февраля" in error


def test_parse_feb_28_at_14() -> None:
    day, slot, error = parse_datetime_phrase("28 февраля в 14ч", today=TODAY, tz=TZ)
    assert error is None
    assert day == date(2025, 2, 28)
    assert slot == time(14, 0)


def test_parse_rejects_quarter_hour() -> None:
    day, slot, error = parse_datetime_phrase("28 февраля в 15:15", today=TODAY, tz=TZ)
    assert error is None
    assert day == date(2025, 2, 28)
    assert slot is None


def test_sunday_is_rejected() -> None:
    # 2 марта 2025 — воскресенье, уже в будущем относительно 25 февраля
    day, slot, error = parse_datetime_phrase("2 марта 2025", today=TODAY, tz=TZ)
    assert day is None
    assert slot is None
    assert error is not None
    assert "выходной" in error


def test_default_timezone_is_chita() -> None:
    assert Settings().timezone_name == "Asia/Chita"
    now = datetime(2025, 2, 25, 12, 0, tzinfo=TZ)
    assert str(now.tzinfo) == "Asia/Chita"
