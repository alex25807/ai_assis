from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from bot.config import Settings
from bot.slots import combine_slot, working_hours


@dataclass(frozen=True)
class CalendarEvent:
    event_id: str
    start: datetime
    end: datetime
    title: str
    chat_id: int | None = None


class CalendarBackend(Protocol):
    def busy_starts(self, day: date) -> set[datetime]: ...

    def book(
        self,
        start: datetime,
        end: datetime,
        title: str,
        description: str,
        chat_id: int,
    ) -> CalendarEvent: ...

    def cancel(self, event_id: str) -> None: ...

    def get(self, event_id: str) -> CalendarEvent | None: ...


class LocalCalendar:
    """SQLite calendar used by default so the live Savvy calendar is never touched."""

    def __init__(self, conn: sqlite3.Connection, tz: ZoneInfo) -> None:
        self.conn = conn
        self.tz = tz
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS calendar_events (
                event_id TEXT PRIMARY KEY,
                starts_at TEXT NOT NULL,
                ends_at TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                chat_id INTEGER,
                status TEXT NOT NULL DEFAULT 'booked'
            )
            """
        )
        self.conn.commit()

    def busy_starts(self, day: date) -> set[datetime]:
        start = datetime.combine(day, datetime.min.time(), tzinfo=self.tz)
        end = start + timedelta(days=1)
        rows = self.conn.execute(
            """
            SELECT starts_at FROM calendar_events
            WHERE status = 'booked' AND starts_at >= ? AND starts_at < ?
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        busy: set[datetime] = set()
        for (raw,) in rows:
            busy.add(datetime.fromisoformat(raw).astimezone(self.tz))
        return busy

    def book(
        self,
        start: datetime,
        end: datetime,
        title: str,
        description: str,
        chat_id: int,
    ) -> CalendarEvent:
        if start in self.busy_starts(start.date()):
            raise SlotTakenError(start)
        event_id = str(uuid.uuid4())
        self.conn.execute(
            """
            INSERT INTO calendar_events
                (event_id, starts_at, ends_at, title, description, chat_id, status)
            VALUES (?, ?, ?, ?, ?, ?, 'booked')
            """,
            (event_id, start.isoformat(), end.isoformat(), title, description, chat_id),
        )
        self.conn.commit()
        return CalendarEvent(event_id, start, end, title, chat_id)

    def cancel(self, event_id: str) -> None:
        self.conn.execute(
            "UPDATE calendar_events SET status = 'cancelled' WHERE event_id = ?",
            (event_id,),
        )
        self.conn.commit()

    def get(self, event_id: str) -> CalendarEvent | None:
        row = self.conn.execute(
            """
            SELECT event_id, starts_at, ends_at, title, chat_id
            FROM calendar_events
            WHERE event_id = ? AND status = 'booked'
            """,
            (event_id,),
        ).fetchone()
        if not row:
            return None
        return CalendarEvent(
            event_id=row[0],
            start=datetime.fromisoformat(row[1]).astimezone(self.tz),
            end=datetime.fromisoformat(row[2]).astimezone(self.tz),
            title=row[3],
            chat_id=row[4],
        )


class SlotTakenError(Exception):
    def __init__(self, start: datetime) -> None:
        super().__init__(f"slot taken: {start.isoformat()}")
        self.start = start


class GoogleCalendar:
    """Optional Google Calendar backend. Never point this at the Savvy production calendar."""

    def __init__(self, calendar_id: str, credentials_path: str, tz: ZoneInfo) -> None:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        scopes = ["https://www.googleapis.com/auth/calendar"]
        creds = service_account.Credentials.from_service_account_file(
            credentials_path, scopes=scopes
        )
        self.service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        self.calendar_id = calendar_id
        self.tz = tz

    def busy_starts(self, day: date) -> set[datetime]:
        start = datetime.combine(day, datetime.min.time(), tzinfo=self.tz)
        end = start + timedelta(days=1)
        result = (
            self.service.events()
            .list(
                calendarId=self.calendar_id,
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        busy: set[datetime] = set()
        for item in result.get("items", []):
            raw = item.get("start", {}).get("dateTime")
            if not raw:
                continue
            busy.add(datetime.fromisoformat(raw).astimezone(self.tz).replace(minute=0, second=0, microsecond=0))
        return busy

    def book(
        self,
        start: datetime,
        end: datetime,
        title: str,
        description: str,
        chat_id: int,
    ) -> CalendarEvent:
        if start in self.busy_starts(start.date()):
            raise SlotTakenError(start)
        body = {
            "summary": title,
            "description": description + f"\nchat_id={chat_id}",
            "start": {"dateTime": start.isoformat(), "timeZone": str(self.tz)},
            "end": {"dateTime": end.isoformat(), "timeZone": str(self.tz)},
        }
        created = (
            self.service.events()
            .insert(calendarId=self.calendar_id, body=body)
            .execute()
        )
        return CalendarEvent(created["id"], start, end, title, chat_id)

    def cancel(self, event_id: str) -> None:
        self.service.events().delete(
            calendarId=self.calendar_id, eventId=event_id
        ).execute()

    def get(self, event_id: str) -> CalendarEvent | None:
        try:
            item = (
                self.service.events()
                .get(calendarId=self.calendar_id, eventId=event_id)
                .execute()
            )
        except Exception:
            return None
        if item.get("status") == "cancelled":
            return None
        raw = item.get("start", {}).get("dateTime")
        if not raw:
            return None
        start = datetime.fromisoformat(raw).astimezone(self.tz)
        end_raw = item.get("end", {}).get("dateTime")
        end = datetime.fromisoformat(end_raw).astimezone(self.tz) if end_raw else start + timedelta(hours=1)
        return CalendarEvent(item["id"], start, end, item.get("summary", ""), None)


def open_sqlite(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def build_calendar(settings: Settings, conn: sqlite3.Connection) -> CalendarBackend:
    if settings.calendar_backend == "google":
        if not settings.google_calendar_id or not settings.google_credentials_path:
            raise RuntimeError(
                "CALENDAR_BACKEND=google requires GOOGLE_CALENDAR_ID and GOOGLE_CREDENTIALS_PATH"
            )
        return GoogleCalendar(
            settings.google_calendar_id,
            settings.google_credentials_path,
            settings.tz,
        )
    return LocalCalendar(conn, settings.tz)


def available_slots(
    calendar: CalendarBackend,
    day: date,
    settings: Settings,
    now: datetime,
) -> list[datetime]:
    busy = calendar.busy_starts(day)
    result: list[datetime] = []
    for slot in working_hours(
        settings.work_start_hour, settings.work_end_hour, settings.slot_minutes
    ):
        start = combine_slot(day, slot, settings.tz)
        if start <= now:
            continue
        if start in busy:
            continue
        result.append(start)
    return result
