from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass
class Lead:
    chat_id: int
    name: str
    phone: str
    address: str
    slot_start: str
    slot_end: str
    event_id: str
    created_at: str


class LeadStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                address TEXT NOT NULL,
                slot_start TEXT NOT NULL,
                slot_end TEXT NOT NULL,
                event_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                chat_id INTEGER PRIMARY KEY,
                step TEXT NOT NULL,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    def save_lead(self, lead: Lead) -> None:
        self.conn.execute(
            """
            INSERT INTO leads
                (chat_id, name, phone, address, slot_start, slot_end, event_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lead.chat_id,
                lead.name,
                lead.phone,
                lead.address,
                lead.slot_start,
                lead.slot_end,
                lead.event_id,
                lead.created_at,
            ),
        )
        self.conn.commit()

    def latest_for_chat(self, chat_id: int) -> Lead | None:
        row = self.conn.execute(
            """
            SELECT chat_id, name, phone, address, slot_start, slot_end, event_id, created_at
            FROM leads WHERE chat_id = ? ORDER BY id DESC LIMIT 1
            """,
            (chat_id,),
        ).fetchone()
        if not row:
            return None
        return Lead(*row)

    def get_session(self, chat_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT step, payload FROM sessions WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        if not row:
            return None
        data = json.loads(row[1])
        data["step"] = row[0]
        return data

    def put_session(self, chat_id: int, step: str, payload: dict[str, Any], now: datetime) -> None:
        stored = dict(payload)
        stored.pop("step", None)
        self.conn.execute(
            """
            INSERT INTO sessions (chat_id, step, payload, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                step = excluded.step,
                payload = excluded.payload,
                updated_at = excluded.updated_at
            """,
            (chat_id, step, json.dumps(stored, ensure_ascii=False), now.isoformat()),
        )
        self.conn.commit()

    def clear_session(self, chat_id: int) -> None:
        self.conn.execute("DELETE FROM sessions WHERE chat_id = ?", (chat_id,))
        self.conn.commit()


def lead_to_dict(lead: Lead) -> dict[str, Any]:
    return asdict(lead)
