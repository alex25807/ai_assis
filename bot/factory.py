from __future__ import annotations

import sqlite3

from bot.calendar_service import build_calendar, open_sqlite
from bot.config import Settings
from bot.engine import DialogueEngine
from bot.faq import FaqResponder
from bot.leads import LeadStore
from bot.notify import MemoryNotifier, TelegramNotifier
from bot.slots import Clock


def build_engine(
    settings: Settings,
    conn: sqlite3.Connection | None = None,
    clock: Clock | None = None,
) -> tuple[DialogueEngine, sqlite3.Connection]:
    connection = conn or open_sqlite(settings.sqlite_path)
    calendar = build_calendar(settings, connection)
    leads = LeadStore(connection)
    faq = FaqResponder(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
    )
    if settings.telegram_bot_token and settings.manager_chat_id:
        notifier = TelegramNotifier(settings.telegram_bot_token, settings.manager_chat_id)
    else:
        notifier = MemoryNotifier()
    engine = DialogueEngine(
        settings=settings,
        calendar=calendar,
        leads=leads,
        faq=faq,
        notifier=notifier,
        clock=clock or Clock(tz=settings.tz),
    )
    return engine, connection
