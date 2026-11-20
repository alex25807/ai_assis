from bot.config import Settings
from bot.factory import build_engine
from bot.calendar_service import LocalCalendar


def test_factory_uses_local_calendar_by_default() -> None:
    settings = Settings(sqlite_path=":memory:")
    engine, conn = build_engine(settings)
    assert settings.calendar_backend == "local"
    assert isinstance(engine.calendar, LocalCalendar)
    conn.close()
