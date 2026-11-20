from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from bot.calendar_service import (
    CalendarBackend,
    SlotTakenError,
    available_slots,
)
from bot.config import Settings
from bot.faq import FaqResponder, detect_intent
from bot.leads import Lead, LeadStore
from bot.notify import MemoryNotifier, Notifier
from bot.slots import (
    Clock,
    format_day,
    format_day_nominative,
    format_slot,
    is_working_day,
    next_working_days,
    parse_datetime_phrase,
)
from bot.validation import is_valid_address, is_valid_name, normalize_phone

GREETING = (
    "Привет! Я ИИ-ассистент компании «Народные окна». Чем могу помочь?"
)

MAIN_MENU: list[list[tuple[str, str]]] = [
    [("Вызвать замерщика", "m"), ("Узнать цены", "p")],
    [("Сроки", "t"), ("Связаться с менеджером", "h")],
]

YES_RE = ("да", "конечно", "давайте", "хочу", "запишите", "ок", "хорошо", "ага")

STEP_PROMPT = {
    "name": "Как вас зовут?",
    "phone": "Напишите контактный номер телефона.",
    "address": "Укажите адрес, где провести замер: город, улица, дом, квартира.",
    "date": "Выберите удобный день для замера. Мы работаем пн–сб с 10:00 до 18:00, воскресенье — выходной.",
    "time": "Выберите свободный час. Слоты — целый час, без минут вроде 15:15.",
    "confirm": "Проверьте данные и подтвердите запись.",
}


@dataclass
class Reply:
    text: str
    buttons: list[list[tuple[str, str]]] = field(default_factory=list)


class DialogueEngine:
    def __init__(
        self,
        settings: Settings,
        calendar: CalendarBackend,
        leads: LeadStore,
        faq: FaqResponder | None = None,
        notifier: Notifier | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.settings = settings
        self.calendar = calendar
        self.leads = leads
        self.faq = faq or FaqResponder()
        self.notifier = notifier or MemoryNotifier()
        self.clock = clock or Clock(tz=settings.tz)

    def handle(self, chat_id: int, text: str | None = None, callback: str | None = None) -> Reply:
        now = self.clock.now()
        session = self.leads.get_session(chat_id) or {"step": "idle"}
        raw = (text or "").strip()

        if raw == "/start" or callback == "start":
            return self._handle_start(chat_id, session, now)
        if callback:
            return self._handle_callback(chat_id, session, callback, now)
        if raw:
            return self._handle_text(chat_id, session, raw, now)
        return self._menu(GREETING)

    def _save(self, chat_id: int, session: dict[str, Any], now: datetime) -> None:
        step = session.get("step", "idle")
        self.leads.put_session(chat_id, step, session, now)

    def _menu(self, text: str) -> Reply:
        return Reply(text, MAIN_MENU)

    def _handle_start(self, chat_id: int, session: dict[str, Any], now: datetime) -> Reply:
        step = session.get("step")
        if step in {"name", "phone", "address", "date", "time", "confirm"}:
            return Reply(
                "У вас есть незавершённая заявка на замер. Продолжить или отменить?",
                [[("Продолжить", "go"), ("Отменить заявку", "x")]],
            )
        if step == "booked" and self._active_booking(session, now):
            slot = session.get("slot")
            when = format_slot(datetime.fromisoformat(slot)) if slot else "выбранное время"
            return Reply(
                f"Вы уже записаны на замер: {when}. Продолжить общение или отменить запись?",
                [[("Продолжить", "go"), ("Отменить запись", "x")]],
            )
        session.clear()
        session["step"] = "idle"
        self._save(chat_id, session, now)
        return self._menu(GREETING)

    def _active_booking(self, session: dict[str, Any], now: datetime) -> bool:
        event_id = session.get("event_id")
        slot = session.get("slot")
        if not event_id or not slot:
            return False
        start = datetime.fromisoformat(slot)
        if start.tzinfo is None:
            start = start.replace(tzinfo=self.settings.tz)
        if start <= now:
            return False
        return self.calendar.get(event_id) is not None

    def _handle_callback(
        self, chat_id: int, session: dict[str, Any], callback: str, now: datetime
    ) -> Reply:
        if callback == "m":
            return self._start_measure(chat_id, session, now)
        if callback == "p":
            return self._info_reply(chat_id, session, self.faq.answer("Сколько стоит замена окон?"), now)
        if callback == "t":
            return self._info_reply(
                chat_id, session, self.faq.answer("Сколько времени займёт замена окон?"), now
            )
        if callback == "h":
            return self._info_reply(chat_id, session, self.faq.answer("Свяжите с менеджером"), now)
        if callback == "go":
            return self._continue(chat_id, session, now)
        if callback == "x":
            return self._cancel(chat_id, session, now)
        if callback == "c":
            return self._confirm(chat_id, session, now)
        if callback == "e":
            session["step"] = "date"
            session.pop("slot", None)
            self._save(chat_id, session, now)
            return self._ask_date(session, now)
        if callback.startswith("d:"):
            return self._apply_date(chat_id, session, callback[2:], now)
        if callback.startswith("s:"):
            return self._apply_slot(chat_id, session, callback[2:], now)
        return self._menu("Не распознал действие. Выберите пункт меню.")

    def _handle_text(
        self, chat_id: int, session: dict[str, Any], text: str, now: datetime
    ) -> Reply:
        step = session.get("step", "idle")
        if step == "name":
            return self._maybe_faq_then(chat_id, session, text, now, self._take_name)
        if step == "phone":
            return self._maybe_faq_then(chat_id, session, text, now, self._take_phone)
        if step == "address":
            return self._maybe_faq_then(chat_id, session, text, now, self._take_address)
        if step == "date":
            return self._maybe_faq_then(chat_id, session, text, now, self._take_date)
        if step == "time":
            return self._maybe_faq_then(chat_id, session, text, now, self._take_time)
        if step == "confirm":
            if text.lower() in YES_RE:
                return self._confirm(chat_id, session, now)
            return self._maybe_faq_then(chat_id, session, text, now, lambda *_: self._confirm_prompt(session))

        if session.get("awaiting_measure") and text.lower().split()[0].rstrip("!,.") in YES_RE:
            return self._start_measure(chat_id, session, now)

        intent = detect_intent(text)
        if intent == "measure":
            return self._start_measure(chat_id, session, now)
        if intent in {"prices", "timeline", "free", "hours", "profile", "address", "manager"}:
            return self._info_reply(chat_id, session, self.faq.answer(text), now)

        if step == "booked" and self._active_booking(session, now):
            reply = self.faq.answer(text)
            when = format_slot(datetime.fromisoformat(session["slot"]))
            return self._menu(
                f"{reply}\n\nНапоминаю: у вас уже есть запись на {when}."
            )

        return self._info_reply(chat_id, session, self.faq.answer(text), now)

    def _maybe_faq_then(
        self,
        chat_id: int,
        session: dict[str, Any],
        text: str,
        now: datetime,
        consume,
    ) -> Reply:
        intent = detect_intent(text)
        if intent in {"prices", "timeline", "free", "hours", "profile", "address", "manager"}:
            answer = self.faq.answer(text)
            follow = STEP_PROMPT[session["step"]]
            extra_buttons = self._step_buttons(session, now)
            return Reply(f"{answer}\n\nПродолжим запись. {follow}", extra_buttons)
        return consume(chat_id, session, text, now)

    def _info_reply(self, chat_id: int, session: dict[str, Any], text: str, now: datetime) -> Reply:
        session["awaiting_measure"] = True
        if session.get("step") not in {"name", "phone", "address", "date", "time", "confirm", "booked"}:
            session["step"] = "idle"
        self._save(chat_id, session, now)
        buttons = [[("Вызвать замерщика", "m")]] + MAIN_MENU[1:]
        return Reply(text, buttons)

    def _start_measure(self, chat_id: int, session: dict[str, Any], now: datetime) -> Reply:
        if session.get("step") == "booked" and self._active_booking(session, now):
            when = format_slot(datetime.fromisoformat(session["slot"]))
            return Reply(
                f"У вас уже есть запись на {when}. Чтобы выбрать другое время, сначала отмените её.",
                [[("Отменить запись", "x"), ("Оставить как есть", "go")]],
            )
        session["step"] = "name"
        session["awaiting_measure"] = False
        session.pop("event_id", None)
        self._save(chat_id, session, now)
        return Reply("Конечно, замер бесплатный и ни к чему не обязывает. Как вас зовут?")

    def _continue(self, chat_id: int, session: dict[str, Any], now: datetime) -> Reply:
        step = session.get("step")
        if step == "booked":
            session["step"] = "booked"
            self._save(chat_id, session, now)
            when = format_slot(datetime.fromisoformat(session["slot"]))
            return self._menu(f"Запись на {when} на месте. Чем ещё помочь?")
        if step in STEP_PROMPT:
            return Reply(STEP_PROMPT[step], self._step_buttons(session, now))
        session["step"] = "idle"
        self._save(chat_id, session, now)
        return self._menu(GREETING)

    def _cancel(self, chat_id: int, session: dict[str, Any], now: datetime) -> Reply:
        event_id = session.get("event_id")
        if event_id:
            self.calendar.cancel(event_id)
        self.leads.clear_session(chat_id)
        return self._menu("Заявку отменил. Чем ещё могу помочь?")

    def _take_name(self, chat_id: int, session: dict[str, Any], text: str, now: datetime) -> Reply:
        if not is_valid_name(text):
            return Reply("Напишите имя текстом, без номера телефона.")
        session["name"] = text.strip()
        session["step"] = "phone"
        self._save(chat_id, session, now)
        return Reply(f"Приятно познакомиться, {session['name']}. Напишите контактный номер телефона.")

    def _take_phone(self, chat_id: int, session: dict[str, Any], text: str, now: datetime) -> Reply:
        phone = normalize_phone(text)
        if not phone:
            return Reply(
                "Этот номер не подходит: нужны 10 цифр российского номера, "
                "не из одних нулей. Пример: +7 914 123-45-67."
            )
        session["phone"] = phone
        session["step"] = "address"
        self._save(chat_id, session, now)
        return Reply("Укажите адрес замера: город, улица, дом, квартира.")

    def _take_address(self, chat_id: int, session: dict[str, Any], text: str, now: datetime) -> Reply:
        if not is_valid_address(text):
            return Reply("Адрес слишком короткий. Напишите город, улицу и дом.")
        session["address"] = text.strip()
        session["step"] = "date"
        self._save(chat_id, session, now)
        return self._ask_date(session, now)

    def _take_date(self, chat_id: int, session: dict[str, Any], text: str, now: datetime) -> Reply:
        parsed, slot_time, error = parse_datetime_phrase(
            text, today=now.date(), tz=self.settings.tz
        )
        if error:
            reply = Reply(error, self._date_buttons(now.date()))
            return reply
        assert parsed is not None
        if slot_time:
            start = datetime.combine(parsed, slot_time, tzinfo=self.settings.tz)
            return self._apply_slot(chat_id, session, start.isoformat(), now, chosen_day=parsed)
        return self._apply_date(chat_id, session, parsed.isoformat(), now)

    def _take_time(self, chat_id: int, session: dict[str, Any], text: str, now: datetime) -> Reply:
        day = date.fromisoformat(session["date"])
        parsed, slot_time, error = parse_datetime_phrase(
            text, today=now.date(), tz=self.settings.tz
        )
        if slot_time is None and error:
            return Reply(error or "Напишите час, например 14:00 или 14ч.", self._slot_buttons(day, now))
        use_day = parsed or day
        if slot_time is None:
            return Reply("Нужен час целиком, например 14:00. Минуты вроде 15:15 не используем.", self._slot_buttons(use_day, now))
        start = datetime.combine(use_day, slot_time, tzinfo=self.settings.tz)
        return self._apply_slot(chat_id, session, start.isoformat(), now, chosen_day=use_day)

    def _apply_date(self, chat_id: int, session: dict[str, Any], iso_day: str, now: datetime) -> Reply:
        day = date.fromisoformat(iso_day)
        if not is_working_day(day):
            return Reply(
                f"{format_day(day).capitalize()} — выходной. Выберите рабочий день.",
                self._date_buttons(now.date()),
            )
        session["date"] = day.isoformat()
        session["step"] = "time"
        self._save(chat_id, session, now)
        slots = available_slots(self.calendar, day, self.settings, now)
        if not slots:
            session["step"] = "date"
            self._save(chat_id, session, now)
            return Reply(
                f"На {format_day(day)} свободных часов нет. Выберите другой день.",
                self._date_buttons(now.date()),
            )
        return Reply(
            f"На {format_day(day)} свободны такие часы. Выберите слот:",
            self._slot_button_rows(slots),
        )

    def _apply_slot(
        self,
        chat_id: int,
        session: dict[str, Any],
        iso_start: str,
        now: datetime,
        chosen_day: date | None = None,
    ) -> Reply:
        start = datetime.fromisoformat(iso_start)
        if start.tzinfo is None:
            start = start.replace(tzinfo=self.settings.tz)
        day = chosen_day or start.date()
        if start.minute != 0 or start.second != 0:
            return Reply(
                "Записываю только на начало часа, например 14:00 или 15:00.",
                self._slot_buttons(day, now),
            )
        if start.hour < self.settings.work_start_hour or start.hour >= self.settings.work_end_hour:
            return Reply(
                "Мы работаем с 10:00 до 18:00. Выберите час в этом диапазоне.",
                self._slot_buttons(day, now),
            )
        free = available_slots(self.calendar, day, self.settings, now)
        if start not in free:
            later = [slot for slot in free if slot > start]
            earlier = [slot for slot in free if slot < start]
            ordered = later + earlier
            alternatives = ", ".join(slot.strftime("%H:%M") for slot in ordered[:4]) or "другой день"
            return Reply(
                f"К сожалению, {format_day(day)} в {start.strftime('%H:%M')} уже занято. "
                f"Могу предложить {alternatives}.",
                self._slot_button_rows(ordered or free) if free else self._date_buttons(now.date()),
            )
        session["date"] = day.isoformat()
        session["slot"] = start.isoformat()
        session["step"] = "confirm"
        self._save(chat_id, session, now)
        return self._confirm_prompt(session)

    def _confirm_prompt(self, session: dict[str, Any]) -> Reply:
        start = datetime.fromisoformat(session["slot"])
        text = (
            "Проверьте заявку — запись появится в календаре только после подтверждения:\n"
            f"• Имя: {session.get('name')}\n"
            f"• Телефон: {session.get('phone')}\n"
            f"• Адрес: {session.get('address')}\n"
            f"• Замер: {format_day_nominative(start.date())} в {start.strftime('%H:%M')}\n\n"
            "Подтвердить?"
        )
        return Reply(text, [[("Подтвердить", "c"), ("Изменить дату", "e")]])

    def _confirm(self, chat_id: int, session: dict[str, Any], now: datetime) -> Reply:
        required = ["name", "phone", "address", "slot"]
        if any(not session.get(key) for key in required):
            session["step"] = "name"
            self._save(chat_id, session, now)
            return Reply("Не хватает данных. Давайте начнём с имени. Как вас зовут?")
        start = datetime.fromisoformat(session["slot"])
        if start.tzinfo is None:
            start = start.replace(tzinfo=self.settings.tz)
        end = start + timedelta(minutes=self.settings.slot_minutes)
        title = f"Замер: {session['name']}"
        description = (
            f"Телефон: {session['phone']}\n"
            f"Адрес: {session['address']}\n"
            f"chat_id: {chat_id}"
        )
        try:
            event = self.calendar.book(start, end, title, description, chat_id)
        except SlotTakenError:
            session["step"] = "time"
            self._save(chat_id, session, now)
            free = available_slots(self.calendar, start.date(), self.settings, now)
            return Reply(
                f"Пока вы подтверждали, {start.strftime('%H:%M')} заняли. Выберите другой час.",
                self._slot_button_rows(free) if free else self._date_buttons(now.date()),
            )
        lead = Lead(
            chat_id=chat_id,
            name=session["name"],
            phone=session["phone"],
            address=session["address"],
            slot_start=start.isoformat(),
            slot_end=end.isoformat(),
            event_id=event.event_id,
            created_at=now.isoformat(),
        )
        self.leads.save_lead(lead)
        self.notifier.notify_lead(lead)
        session["step"] = "booked"
        session["event_id"] = event.event_id
        session["awaiting_measure"] = False
        self._save(chat_id, session, now)
        return self._menu(
            f"Вы записаны на бесплатный замер на {format_day(start.date())} в {start.strftime('%H:%M')}. "
            "Если понадобится перенести визит, напишите. Ждём вас!"
        )

    def _ask_date(self, session: dict[str, Any], now: datetime) -> Reply:
        return Reply(STEP_PROMPT["date"], self._date_buttons(now.date()))

    def _date_buttons(self, today: date) -> list[list[tuple[str, str]]]:
        days = next_working_days(today, 4)
        row = [(f"{d.day:02d}.{d.month:02d}", f"d:{d.isoformat()}") for d in days]
        return [row[:2], row[2:]]

    def _slot_buttons(self, day: date, now: datetime) -> list[list[tuple[str, str]]]:
        return self._slot_button_rows(available_slots(self.calendar, day, self.settings, now))

    def _slot_button_rows(self, slots: list[datetime]) -> list[list[tuple[str, str]]]:
        buttons = [(s.strftime("%H:%M"), f"s:{s.isoformat()}") for s in slots]
        rows: list[list[tuple[str, str]]] = []
        for i in range(0, len(buttons), 4):
            rows.append(buttons[i : i + 4])
        return rows

    def _step_buttons(self, session: dict[str, Any], now: datetime) -> list[list[tuple[str, str]]]:
        step = session.get("step")
        if step == "date":
            return self._date_buttons(now.date())
        if step == "time" and session.get("date"):
            return self._slot_buttons(date.fromisoformat(session["date"]), now)
        if step == "confirm":
            return [[("Подтвердить", "c"), ("Изменить дату", "e")]]
        return []
