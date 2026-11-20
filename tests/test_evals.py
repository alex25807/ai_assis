from __future__ import annotations

import json
from datetime import timedelta

import pytest

from bot.engine import DialogueEngine
from bot.paths import EVALS_DIR


def _book_other_chat(engine: DialogueEngine) -> None:
    start = engine.clock.now().replace(day=28, hour=14, minute=0, second=0, microsecond=0)
    engine.calendar.book(start, start + timedelta(hours=1), "занято", "", 99)


SETUPS = {
    "book_other_chat_feb28_14": _book_other_chat,
}


def _load_cases() -> list[dict]:
    path = EVALS_DIR / "dialogues.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _load_cases(), ids=lambda case: case["id"])
def test_eval_dialogue(engine: DialogueEngine, case: dict) -> None:
    setup = case.get("setup")
    if setup:
        SETUPS[setup](engine)
        reply = None
        for step in case["steps"]:
            if "callback" in step:
                reply = engine.handle(1, callback=step["callback"])
            elif "user" in step:
                reply = engine.handle(1, text=step["user"])
            _assert_step(reply, step)
        assert reply is not None


def _assert_step(reply, step: dict) -> None:
    if "expect_contains" not in step and "expect_not_contains" not in step:
        return
    text = reply.text
    for needle in step.get("expect_contains", []):
        assert needle in text, f"missing {needle!r} in {text!r}"
    for needle in step.get("expect_not_contains", []):
        assert needle not in text, f"unexpected {needle!r} in {text!r}"
    if "expect_buttons" in step:
        labels = [label for row in reply.buttons for label, _ in row]
        for name in step["expect_buttons"]:
            assert name in labels
