from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher

from bot.config import Settings, load_dotenv
from bot.factory import build_engine
from bot.handlers import attach_engine, router


async def run() -> None:
    load_dotenv()
    settings = Settings.from_env()
    token = settings.telegram_bot_token
    if not token:
        raise SystemExit(
            "Нужен TELEGRAM_BOT_TOKEN тестового бота. "
            "Не подставляйте токен живого Savvy-бота @narrodnyeoknaa_bot — "
            "Telegram отдаёт апдейты только одному получателю."
        )
    if settings.calendar_backend == "google":
        logging.warning(
            "Google Calendar включён. Убедитесь, что GOOGLE_CALENDAR_ID "
            "не указывает на календарь живого Savvy-бота."
        )

    engine, _conn = build_engine(settings)
    attach_engine(engine)

    bot = Bot(token=token)
    dp = Dispatcher()
    dp.include_router(router)
    logging.info("Starting polling on a non-Savvy token")
    await dp.start_polling(bot)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == "__main__":
    main()
