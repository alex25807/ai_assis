from __future__ import annotations

from dataclasses import dataclass, field

from bot.leads import Lead


@dataclass
class Notification:
    title: str
    body: str


class Notifier:
    def notify_lead(self, lead: Lead) -> None:
        raise NotImplementedError


@dataclass
class MemoryNotifier(Notifier):
    messages: list[Notification] = field(default_factory=list)

    def notify_lead(self, lead: Lead) -> None:
        body = (
            f"Новая заявка на замер\n"
            f"Имя: {lead.name}\n"
            f"Телефон: {lead.phone}\n"
            f"Адрес: {lead.address}\n"
            f"Слот: {lead.slot_start}\n"
            f"event_id: {lead.event_id}\n"
            f"chat_id: {lead.chat_id}"
        )
        self.messages.append(Notification("Новая заявка на замер", body))


class TelegramNotifier(Notifier):
    def __init__(self, token: str, manager_chat_id: int) -> None:
        self.token = token
        self.manager_chat_id = manager_chat_id
        self.fallback = MemoryNotifier()

    def notify_lead(self, lead: Lead) -> None:
        self.fallback.notify_lead(lead)
        try:
            import httpx

            text = self.fallback.messages[-1].body
            httpx.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": self.manager_chat_id, "text": text},
                timeout=10.0,
            )
        except Exception:
            pass
