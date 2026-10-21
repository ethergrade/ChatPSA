"""Append-only conversation history with rename support and no deletion API."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .config import project_root


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _default_title(question: str) -> str:
    compact = " ".join(question.split())
    return (compact[:77] + "…") if len(compact) > 78 else compact


class HistoryStore:
    def __init__(self, path: Path | None = None) -> None:
        configured = os.environ.get("CHATPSA_HISTORY_DB", "").strip()
        self.path = path or (
            Path(configured).expanduser()
            if configured
            else project_root() / "data" / "history.sqlite3"
        )

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                owner_email TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY(conversation_id) REFERENCES conversations(id)
            );
            CREATE INDEX IF NOT EXISTS messages_conversation_idx
                ON messages(conversation_id, id);
            """
        )
        return connection

    def append_exchange(
        self,
        *,
        owner_email: str,
        question: str,
        answer: str,
        metadata: dict[str, object],
        conversation_id: str | None = None,
    ) -> dict[str, str]:
        connection = self._connect()
        try:
            now = _now()
            if conversation_id:
                row = connection.execute(
                    "SELECT id, title FROM conversations WHERE id=? AND owner_email=?",
                    (conversation_id, owner_email.casefold()),
                ).fetchone()
                if row is None:
                    raise ValueError("Conversazione non trovata")
                title = str(row["title"])
            else:
                conversation_id = uuid4().hex
                title = _default_title(question) or "Nuova indagine"
                connection.execute(
                    "INSERT INTO conversations VALUES (?, ?, ?, ?, ?)",
                    (conversation_id, owner_email.casefold(), title, now, now),
                )
            connection.execute(
                "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, 'user', ?, ?)",
                (conversation_id, question, now),
            )
            connection.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata_json, created_at) VALUES (?, 'assistant', ?, ?, ?)",
                (
                    conversation_id,
                    answer,
                    json.dumps(metadata, ensure_ascii=False, default=str),
                    now,
                ),
            )
            connection.execute(
                "UPDATE conversations SET updated_at=? WHERE id=?",
                (now, conversation_id),
            )
            connection.commit()
            return {"id": conversation_id, "title": title, "updated_at": now}
        finally:
            connection.close()

    def list_conversations(self, owner_email: str) -> list[dict[str, str]]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT id, title, created_at, updated_at FROM conversations WHERE owner_email=? ORDER BY updated_at DESC",
                (owner_email.casefold(),),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            connection.close()

    def get_messages(self, owner_email: str, conversation_id: str) -> list[dict[str, object]]:
        connection = self._connect()
        try:
            owned = connection.execute(
                "SELECT 1 FROM conversations WHERE id=? AND owner_email=?",
                (conversation_id, owner_email.casefold()),
            ).fetchone()
            if owned is None:
                raise ValueError("Conversazione non trovata")
            rows = connection.execute(
                "SELECT role, content, metadata_json, created_at FROM messages WHERE conversation_id=? ORDER BY id",
                (conversation_id,),
            ).fetchall()
            result: list[dict[str, object]] = []
            for row in rows:
                item = dict(row)
                item["metadata"] = json.loads(item.pop("metadata_json"))
                result.append(item)
            return result
        finally:
            connection.close()

    def rename(self, owner_email: str, conversation_id: str, title: str) -> dict[str, str]:
        title = " ".join(title.split())
        if not title or len(title) > 120:
            raise ValueError("Il titolo deve contenere da 1 a 120 caratteri")
        connection = self._connect()
        try:
            cursor = connection.execute(
                "UPDATE conversations SET title=?, updated_at=? WHERE id=? AND owner_email=?",
                (title, _now(), conversation_id, owner_email.casefold()),
            )
            if cursor.rowcount != 1:
                raise ValueError("Conversazione non trovata")
            connection.commit()
            return {"id": conversation_id, "title": title}
        finally:
            connection.close()
