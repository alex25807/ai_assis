from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from bot.paths import DATA_DIR, ROOT


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name, default)
    if value is None:
        return None
    value = value.strip()
    return value or None


@dataclass(frozen=True)
class Settings:
    """Runtime settings. TELEGRAM_BOT_TOKEN must never be the Savvy bot token."""

    timezone_name: str = "Asia/Chita"
    work_start_hour: int = 10
    work_end_hour: int = 18
    slot_minutes: int = 60
    calendar_backend: str = "local"
    sqlite_path: str = str(DATA_DIR / "assistant.db")
    telegram_bot_token: str | None = None
    manager_chat_id: int | None = None
    llm_api_key: str | None = None
    llm_base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    llm_model: str = "qwen-plus"
    google_calendar_id: str | None = None
    google_credentials_path: str | None = None

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    @classmethod
    def from_env(cls) -> "Settings":
        manager = _env("MANAGER_CHAT_ID")
        sqlite = _env("SQLITE_PATH") or str(DATA_DIR / "assistant.db")
        creds = _env("GOOGLE_CREDENTIALS_PATH")
        if creds:
            creds_path = str(Path(creds))
        else:
            creds_path = None
        return cls(
            timezone_name=_env("TZ_NAME") or "Asia/Chita",
            calendar_backend=(_env("CALENDAR_BACKEND") or "local").lower(),
            sqlite_path=sqlite,
            telegram_bot_token=_env("TELEGRAM_BOT_TOKEN"),
            manager_chat_id=int(manager) if manager else None,
            llm_api_key=_env("LLM_API_KEY"),
            llm_base_url=_env("LLM_BASE_URL")
            or "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            llm_model=_env("LLM_MODEL") or "qwen-plus",
            google_calendar_id=_env("GOOGLE_CALENDAR_ID"),
            google_credentials_path=creds_path,
        )


def load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)
