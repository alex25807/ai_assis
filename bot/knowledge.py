from __future__ import annotations

from functools import lru_cache

from bot.paths import KB_DIR, PROMPTS_DIR


@lru_cache(maxsize=1)
def company_text() -> str:
    return (KB_DIR / "company.md").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def faq_text() -> str:
    return (KB_DIR / "faq.md").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def system_prompt() -> str:
    return (PROMPTS_DIR / "system.md").read_text(encoding="utf-8")


def knowledge_bundle() -> str:
    return f"{system_prompt()}\n\n# База знаний\n\n{company_text()}\n\n{faq_text()}"
