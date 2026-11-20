from datetime import datetime, timedelta

from bot.calendar_service import SlotTakenError, available_slots
from bot.engine import DialogueEngine, GREETING
from bot.notify import MemoryNotifier


def test_start_has_no_wrapping_quotes(engine: DialogueEngine) -> None:
    reply = engine.handle(1, text="/start")
    assert reply.text == GREETING
    assert not reply.text.startswith('"')
    labels = [label for row in reply.buttons for label, _ in row]
    assert "Вызвать замерщика" in labels


def test_measure_collects_one_field_at_a_time(engine: DialogueEngine) -> None:
    reply = engine.handle(1, text="Можно вызвать замерщика?")
    assert "Как вас зовут" in reply.text
    assert "телефон" not in reply.text.lower() or "Как вас зовут" in reply.text
    assert "1." not in reply.text


def test_faq_during_booking_keeps_name_step(engine: DialogueEngine) -> None:
    engine.handle(1, callback="m")
    reply = engine.handle(1, text="Это точно бесплатная услуга?")
    assert "бесплат" in reply.text.lower()
    assert "Как вас зовут" in reply.text
    assert "1. Ваше имя" not in reply.text


def test_price_answer_has_no_invented_rub(engine: DialogueEngine) -> None:
    reply = engine.handle(1, text="Мне надо заменить 3 окна. Сколько это будет стоить?")
    assert "Стоимость замены окон" in reply.text
    assert "Gealan" in reply.text
    assert "₽" not in reply.text
    assert "9:00" not in reply.text


def test_rejects_zero_phone_and_does_not_book(engine: DialogueEngine) -> None:
    engine.handle(1, callback="m")
    engine.handle(1, text="Александр")
    reply = engine.handle(1, text="0000000")
    assert "не подходит" in reply.text
    assert engine.calendar.busy_starts(engine.clock.now().date()) == set()
    assert isinstance(engine.notifier, MemoryNotifier)
    assert engine.notifier.messages == []


def test_full_booking_requires_confirm_then_notifies(engine: DialogueEngine) -> None:
    engine.handle(1, callback="m")
    engine.handle(1, text="Александр")
    engine.handle(1, text="+79144976060")
    engine.handle(1, text="Чита, ул. Бабушкина, 153, кв. 10")
    reply = engine.handle(1, text="28 февраля в 14ч")
    assert "Подтвердить" in reply.text
    assert "Вы записаны" not in reply.text
    assert engine.leads.latest_for_chat(1) is None

    done = engine.handle(1, callback="c")
    assert "Вы записаны" in done.text
    assert "14:00" in done.text
    lead = engine.leads.latest_for_chat(1)
    assert lead is not None
    assert lead.phone == "+79144976060"
    assert "Бабушкина" in lead.address
    assert isinstance(engine.notifier, MemoryNotifier)
    assert len(engine.notifier.messages) == 1


def test_start_after_booking_does_not_double_book(engine: DialogueEngine) -> None:
    engine.handle(1, callback="m")
    engine.handle(1, text="Александр")
    engine.handle(1, text="+79144976060")
    engine.handle(1, text="Чита, ул. Бабушкина, 153")
    engine.handle(1, text="28 февраля в 14ч")
    engine.handle(1, callback="c")

    restart = engine.handle(1, text="/start")
    assert "уже записаны" in restart.text
    labels = [label for row in restart.buttons for label, _ in row]
    assert "Продолжить" in labels
    assert "Отменить запись" in labels

    busy = engine.calendar.busy_starts(datetime(2025, 2, 28).date())
    assert len(busy) == 1


def test_occupied_slot_suggests_next_whole_hour(engine: DialogueEngine) -> None:
    engine.handle(1, callback="m")
    engine.handle(1, text="Александр")
    engine.handle(1, text="+79144976060")
    engine.handle(1, text="Чита, ул. Бабушкина, 153")
    engine.handle(1, text="28 февраля в 14ч")
    engine.handle(1, callback="c")

    engine.handle(2, callback="m")
    engine.handle(2, text="Мария")
    engine.handle(2, text="89141234567")
    engine.handle(2, text="Чита, Ленина 1")
    reply = engine.handle(2, text="28 февраля в 14ч")
    assert "занято" in reply.text
    assert "15:00" in reply.text
    assert "15:15" not in reply.text


def test_cancel_frees_slot(engine: DialogueEngine) -> None:
    engine.handle(1, callback="m")
    engine.handle(1, text="Александр")
    engine.handle(1, text="+79144976060")
    engine.handle(1, text="Чита, ул. Бабушкина, 153")
    engine.handle(1, text="28 февраля в 14ч")
    engine.handle(1, callback="c")
    engine.handle(1, text="/start")
    engine.handle(1, callback="x")
    day = datetime(2025, 2, 28).date()
    assert engine.calendar.busy_starts(day) == set()
    free = available_slots(engine.calendar, day, engine.settings, engine.clock.now())
    assert any(slot.hour == 14 for slot in free)


def test_cannot_book_without_address(engine: DialogueEngine) -> None:
    session = {
        "step": "confirm",
        "name": "Александр",
        "phone": "+79144976060",
        "slot": engine.clock.now().replace(day=28, hour=14, minute=0, second=0, microsecond=0).isoformat(),
    }
    engine.leads.put_session(1, "confirm", session, engine.clock.now())
    reply = engine.handle(1, callback="c")
    assert "Вы записаны" not in reply.text
    assert engine.leads.latest_for_chat(1) is None


def test_slot_taken_error_message(engine: DialogueEngine) -> None:
    start = engine.clock.now().replace(day=28, hour=14, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=1)
    engine.calendar.book(start, end, "busy", "", 99)
    try:
        engine.calendar.book(start, end, "busy2", "", 100)
        assert False, "expected SlotTakenError"
    except SlotTakenError as exc:
        assert exc.start == start
