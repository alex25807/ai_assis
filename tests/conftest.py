from __future__ import annotations

from datetime import datetime

import pytest

from bot.calendar_service import LocalCalendar, open_sqlite
from bot.config import Settings
from bot.engine import DialogueEngine
from bot.faq import FaqResponder
from bot.leads import LeadStore
from bot.notify import MemoryNotifier
from bot.slots import Clock


FROZEN = datetime(2025, 2, 25, 12, 0, tzinfo=None)


@pytest.fixture
def settings() -> Settings:
    return Settings(sqlite_path=":memory:", calendar_backend="local")


@pytest.fixture
def engine(settings: Settings) -> DialogueEngine:
    conn = open_sqlite(":memory:")
    calendar = LocalCalendar(conn, settings.tz)
    leads = LeadStore(conn)
    return DialogueEngine(
        settings=settings,
        calendar=calendar,
        leads=leads,
        faq=FaqResponder(),
        notifier=MemoryNotifier(),
        clock=Clock(now=FROZEN, tz=settings.tz),
    )
