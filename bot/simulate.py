from __future__ import annotations

"""Текстовый прогон диалога без Telegram. Не использует токен Savvy."""

from bot.config import Settings
from bot.factory import build_engine
from bot.slots import Clock


def run_script(lines: list[str], chat_id: int = 1, clock: Clock | None = None) -> list[str]:
    settings = Settings(sqlite_path=":memory:", calendar_backend="local")
    engine, _ = build_engine(settings, clock=clock or Clock(tz=settings.tz))
    log: list[str] = []
    for line in lines:
        if line.startswith("cb:"):
            reply = engine.handle(chat_id, callback=line[3:])
            shown = f"user[callback]: {line[3:]}"
        else:
            reply = engine.handle(chat_id, text=line)
            shown = f"user: {line}"
        buttons = []
        for row in reply.buttons:
            buttons.extend(f"[{label}]" for label, _ in row)
        log.append(shown)
        log.append(f"bot: {reply.text}")
        if buttons:
            log.append("buttons: " + " ".join(buttons))
        log.append("")
    return log


def main() -> None:
    from datetime import datetime

    clock = Clock(now=datetime(2025, 2, 25, 12, 0), tz=Settings().tz)
    script = [
        "/start",
        "Мне надо заменить 3 окна. Сколько это будет стоить?",
        "cb:m",
        "Александр",
        "0000000",
        "+7 914 497-60-60",
        "Чита, ул. Бабушкина, 153, кв. 4",
        "29 февраля",
        "28 февраля в 14ч",
        "cb:c",
        "/start",
    ]
    print("\n".join(run_script(script, clock=clock)))


if __name__ == "__main__":
    main()
