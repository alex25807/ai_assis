from __future__ import annotations

import calendar
import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

MONTHS = {
    "январ": 1,
    "феврал": 2,
    "март": 3,
    "апрел": 4,
    "мая": 5,
    "май": 5,
    "июн": 6,
    "июл": 7,
    "август": 8,
    "сентябр": 9,
    "октябр": 10,
    "ноябр": 11,
    "декабр": 12,
}


class Clock:
    def __init__(self, now: datetime | None = None, tz: ZoneInfo | None = None) -> None:
        self._now = now
        self.tz = tz or ZoneInfo("Asia/Chita")

    def now(self) -> datetime:
        if self._now is not None:
            current = self._now
            if current.tzinfo is None:
                return current.replace(tzinfo=self.tz)
            return current.astimezone(self.tz)
        return datetime.now(self.tz)


def is_working_day(day: date) -> bool:
    return day.weekday() != 6  # Sunday is 6


def working_hours(start_hour: int = 10, end_hour: int = 18, slot_minutes: int = 60) -> list[time]:
    slots: list[time] = []
    minutes = start_hour * 60
    end_minutes = end_hour * 60
    while minutes + slot_minutes <= end_minutes:
        slots.append(time(minutes // 60, minutes % 60))
        minutes += slot_minutes
    return slots


def combine_slot(day: date, slot: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, slot, tzinfo=tz)


def next_working_days(start: date, count: int = 5) -> list[date]:
    days: list[date] = []
    cursor = start
    while len(days) < count:
        if is_working_day(cursor):
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def nearest_working_day(day: date) -> date:
    cursor = day
    for _ in range(14):
        if is_working_day(cursor):
            return cursor
        cursor += timedelta(days=1)
    return day


def validate_calendar_day(year: int, month: int, day: int) -> tuple[date | None, str | None]:
    last = calendar.monthrange(year, month)[1]
    if day > last:
        if month == 2 and day == 29 and not calendar.isleap(year):
            suggestion = date(year, 2, 28)
            if not is_working_day(suggestion):
                suggestion = nearest_working_day(suggestion)
            weekday = _weekday_ru(suggestion)
            return None, (
                f"К сожалению, 29 февраля в этом году не существует, "
                f"так как {year} год не является високосным. "
                f"Возможно, вы имели в виду {weekday}, {suggestion.day} февраля?"
            )
        return None, "Такой даты не существует. Уточните, пожалуйста, день."
    try:
        return date(year, month, day), None
    except ValueError:
        return None, "Такой даты не существует. Уточните, пожалуйста, день."


def _weekday_ru(day: date) -> str:
    names = [
        "понедельник",
        "вторник",
        "среду",
        "четверг",
        "пятницу",
        "субботу",
        "воскресенье",
    ]
    return names[day.weekday()]


def _month_ru(day: date) -> str:
    months = [
        "января",
        "февраля",
        "марта",
        "апреля",
        "мая",
        "июня",
        "июля",
        "августа",
        "сентября",
        "октября",
        "ноября",
        "декабря",
    ]
    return months[day.month - 1]


def format_day(day: date) -> str:
    return f"{_weekday_ru(day)}, {day.day} {_month_ru(day)}"


def format_day_nominative(day: date) -> str:
    names = [
        "понедельник",
        "вторник",
        "среда",
        "четверг",
        "пятница",
        "суббота",
        "воскресенье",
    ]
    return f"{names[day.weekday()]}, {day.day} {_month_ru(day)}"


def parse_datetime_phrase(
    text: str, *, today: date, tz: ZoneInfo
) -> tuple[date | None, time | None, str | None]:
    raw = (text or "").strip().lower()
    if not raw:
        return None, None, "Напишите дату, например: 28 февраля."

    iso = re.search(r"(20\d{2})-(\d{1,2})-(\d{1,2})", raw)
    if iso:
        year, month, day = (int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        parsed, error = validate_calendar_day(year, month, day)
        slot = _parse_time(raw)
        return parsed, slot, error

    year_match = re.search(r"20\d{2}", raw)
    year = int(year_match.group(0)) if year_match else today.year

    without_time = re.sub(r"\b\d{1,2}[:.]\d{2}\b", " ", raw)
    without_time = re.sub(r"\b\d{1,2}\s*(?:ч(?:аса|ов)?|h)\b", " ", without_time)
    without_time = re.sub(r"20\d{2}", " ", without_time)
    day_match = re.search(r"\b(\d{1,2})\b", without_time)
    month = _parse_month(without_time)
    if day_match and month:
        day = int(day_match.group(1))
        parsed, error = validate_calendar_day(year, month, day)
        if parsed is None:
            return None, None, error
        if parsed < today and year == today.year and not year_match:
            parsed, error = validate_calendar_day(year + 1, month, day)
            if parsed is None:
                return None, None, error
        if parsed.weekday() == 6:
            nxt = nearest_working_day(parsed + timedelta(days=1))
            return None, None, (
                f"{format_day(parsed).capitalize()} — выходной. "
                f"Ближайший рабочий день: {format_day(nxt)}."
            )
        return parsed, _parse_time(raw), None

    if "сегодня" in raw:
        if not is_working_day(today):
            nxt = nearest_working_day(today + timedelta(days=1))
            return None, None, f"Сегодня выходной. Могу предложить {format_day(nxt)}."
        return today, _parse_time(raw), None
    if "завтра" in raw:
        tomorrow = today + timedelta(days=1)
        if not is_working_day(tomorrow):
            nxt = nearest_working_day(tomorrow + timedelta(days=1))
            return None, None, f"Завтра выходной. Могу предложить {format_day(nxt)}."
        return tomorrow, _parse_time(raw), None

    return None, None, "Не распознал дату. Напишите, например: 28 февраля."


def _parse_month(text: str) -> int | None:
    # Longer stems first so «май» does not steal «марта».
    for stem, month in sorted(MONTHS.items(), key=lambda item: -len(item[0])):
        if stem in text:
            return month
    return None


def _parse_time(text: str) -> time | None:
    match = re.search(r"\b(\d{1,2})[:.](\d{2})\b", text)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        if minute != 0:
            return None  # reject 15:15 — only whole hours
        if 0 <= hour <= 23:
            return time(hour, 0)
        return None
    match = re.search(r"\b(\d{1,2})\s*(?:ч(?:аса|ов)?|h)\b", text)
    if match:
        hour = int(match.group(1))
        if 0 <= hour <= 23:
            return time(hour, 0)
    return None


def format_slot(start: datetime) -> str:
    return start.strftime("%d.%m.%Y в %H:%M")
