from __future__ import annotations

import re

import httpx

from bot.knowledge import knowledge_bundle


PRICE_RE = re.compile(
    r"цен[аыеу]|стоим|сколько.{0,24}сто[ии]т|почём|почем|прайс",
    re.IGNORECASE | re.DOTALL,
)
TIME_RE = re.compile(
    r"сколько\s+врем|срок|как\s+долго|займ(ёт|ет)|день\s+работ",
    re.IGNORECASE,
)
MEASURE_RE = re.compile(
    r"замер|записать|запис(ать|аться|ите)|вызвать\s+замер|хочу\s+замер",
    re.IGNORECASE,
)
MANAGER_RE = re.compile(
    r"менеджер|оператор|человек|позвон|живой",
    re.IGNORECASE,
)
FREE_RE = re.compile(r"бесплатн|платн", re.IGNORECASE)
HOURS_RE = re.compile(r"график|до\s+скольк|часы\s+работ|когда\s+работ", re.IGNORECASE)
PROFILE_RE = re.compile(r"профиль|gealan|геалан|из\s+чего", re.IGNORECASE)
ADDRESS_RE = re.compile(r"адрес|где\s+находи|офис", re.IGNORECASE)


PRICE_ANSWER = (
    "Стоимость замены окон зависит от размеров проёмов, типа стеклопакета, "
    "профиля Gealan, дополнительных опций и сложности демонтажа.\n\n"
    "Точную сумму назовём в день бесплатного замера — он ни к чему не обязывает. "
    "В работы входит монтаж, вынос мусора после установки бесплатный.\n\n"
    "Могу записать вас на замер."
)

TIME_ANSWER = (
    "Замена нескольких окон в квартире обычно занимает 1 рабочий день. "
    "Точное время зависит от сложности демонтажа, опций и условий на объекте "
    "(этаж, доступ к проёмам).\n\n"
    "Специалисты работают аккуратно, чтобы минимизировать неудобства. "
    "Могу записать вас на замер, чтобы согласовать удобное время."
)

FREE_ANSWER = (
    "Да, вызов замерщика полностью бесплатный и ни к чему не обязывает. "
    "Специалист приедет, снимет размеры и посчитает стоимость в тот же день."
)

HOURS_ANSWER = (
    "Мы работаем с понедельника по субботу с 10:00 до 18:00. Воскресенье — выходной."
)

PROFILE_ANSWER = (
    "Ставим пластиковые окна из профиля Gealan — это основная линейка компании «Народные окна»."
)

ADDRESS_ANSWER = (
    "Офис в Чите: ул. Бабушкина, 153, ТЦ «Ся-Ян», 3 этаж, офис 4. "
    "Телефоны: +7 (3022) 72-02-72, +7 (914) 497-60-60, +7 (924) 812-02-72."
)

MANAGER_ANSWER = (
    "Могу передать заявку менеджеру. Позвоните нам: +7 (3022) 72-02-72, "
    "+7 (914) 497-60-60, +7 (924) 812-02-72. Email: market@oknagealan.ru."
)

GENERIC_ANSWER = (
    "Я ассистент компании «Народные окна» в Чите: окна Gealan, остекление балконов и лоджий, двери. "
    "Замер бесплатный, расчёт стоимости — в день замера. Чем помочь: цены, сроки или запись на замер?"
)


def detect_intent(text: str) -> str:
    raw = text or ""
    if MEASURE_RE.search(raw):
        return "measure"
    if PRICE_RE.search(raw):
        return "prices"
    if TIME_RE.search(raw):
        return "timeline"
    if MANAGER_RE.search(raw):
        return "manager"
    if FREE_RE.search(raw):
        return "free"
    if HOURS_RE.search(raw):
        return "hours"
    if PROFILE_RE.search(raw):
        return "profile"
    if ADDRESS_RE.search(raw):
        return "address"
    return "unknown"


def canned_answer(intent: str) -> str | None:
    mapping = {
        "prices": PRICE_ANSWER,
        "timeline": TIME_ANSWER,
        "free": FREE_ANSWER,
        "hours": HOURS_ANSWER,
        "profile": PROFILE_ANSWER,
        "address": ADDRESS_ANSWER,
        "manager": MANAGER_ANSWER,
    }
    return mapping.get(intent)


class FaqResponder:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "",
        model: str = "qwen-plus",
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def answer(self, question: str) -> str:
        intent = detect_intent(question)
        canned = canned_answer(intent)
        if canned:
            return canned
        if self.api_key and self.base_url:
            llm = self._llm_answer(question)
            if llm:
                return llm
        return GENERIC_ANSWER

    def _llm_answer(self, question: str) -> str | None:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": knowledge_bundle()},
                {"role": "user", "content": question},
            ],
            "temperature": 0.2,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = httpx.post(url, json=payload, headers=headers, timeout=20.0)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception:
            return None
