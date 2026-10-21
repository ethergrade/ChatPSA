"""Local approval queue for proposed HaloPSA configuration changes."""

from __future__ import annotations

import json
import os
import smtplib
import sqlite3
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path
from uuid import uuid4

from .config import project_root

CHANGE_TERMS = (
    "crea status",
    "creare status",
    "crea ticket type",
    "creare ticket type",
    "crea tipo ticket",
    "creare tipo ticket",
    "crea categoria",
    "creare categoria",
    "crea regola",
    "creare regola",
    "modifica regola",
    "modificare regola",
    "crea rule",
    "modifica rule",
    "crea workflow",
    "modifica workflow",
    "cambia workflow",
    "cambia configurazione",
    "modifica configurazione",
    "crea kb",
    "crea una kb",
    "creare kb",
    "crea knowledge base",
    "crea articolo",
    "creare articolo",
    "pubblica articolo",
    "modifica articolo",
    "release notes",
    "release note",
    "note di rilascio",
)


@dataclass(frozen=True)
class Actor:
    name: str
    email: str
    role: str = "agent"


def is_change_request(message: str) -> bool:
    lowered = message.casefold()
    return any(term in lowered for term in CHANGE_TERMS)


def approver_emails() -> frozenset[str]:
    return frozenset(
        value.strip().casefold()
        for value in os.environ.get("CHATPSA_APPROVER_EMAILS", "").split(",")
        if value.strip()
    )


def is_approver(actor: Actor) -> bool:
    return actor.role == "approver" and actor.email.casefold() in approver_emails()


class ApprovalStore:
    def __init__(self, path: Path | None = None) -> None:
        configured = os.environ.get("CHATPSA_APPROVAL_DB", "").strip()
        self.path = path or (
            Path(configured).expanduser()
            if configured
            else project_root() / "data" / "approvals.sqlite3"
        )

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS approval_requests (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                requester_name TEXT NOT NULL,
                requester_email TEXT NOT NULL,
                question TEXT NOT NULL,
                proposed_answer TEXT NOT NULL,
                sources_json TEXT NOT NULL,
                status TEXT NOT NULL,
                reviewer_email TEXT,
                reviewed_at TEXT
            )
            """
        )
        existing = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(approval_requests)"
            ).fetchall()
        }
        migrations = {
            "action_type": "TEXT",
            "payload_json": "TEXT NOT NULL DEFAULT '{}'",
            "execution_enabled": "INTEGER NOT NULL DEFAULT 0",
            "result_json": "TEXT",
            "error_message": "TEXT",
        }
        for column, definition in migrations.items():
            if column not in existing:
                connection.execute(
                    f"ALTER TABLE approval_requests ADD COLUMN {column} {definition}"
                )
        connection.commit()
        return connection

    def create(
        self,
        *,
        actor: Actor,
        question: str,
        proposed_answer: str,
        sources: list[dict[str, str]],
        action_type: str | None = None,
        payload: dict[str, object] | None = None,
        execution_enabled: bool = False,
    ) -> dict[str, object]:
        request_id = uuid4().hex
        created_at = datetime.now(UTC).isoformat()
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO approval_requests (
                    id, created_at, requester_name, requester_email, question,
                    proposed_answer, sources_json, status, action_type,
                    payload_json, execution_enabled
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                """,
                (
                    request_id,
                    created_at,
                    actor.name,
                    actor.email,
                    question,
                    proposed_answer,
                    json.dumps(sources, ensure_ascii=False),
                    action_type,
                    json.dumps(payload or {}, ensure_ascii=False),
                    int(execution_enabled),
                ),
            )
            connection.commit()
        finally:
            connection.close()
        return {
            "id": request_id,
            "status": "pending",
            "created_at": created_at,
            "action_type": action_type,
            "execution_enabled": execution_enabled,
        }

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, object]:
        item = dict(row)
        for source, target in (
            ("sources_json", "sources"),
            ("payload_json", "payload"),
            ("result_json", "result"),
        ):
            raw = item.pop(source, None)
            item[target] = json.loads(raw) if raw else None
        item["execution_enabled"] = bool(item.get("execution_enabled"))
        return item

    def list_requests(self, *, limit: int = 100) -> list[dict[str, object]]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM approval_requests ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
            return [self._decode(row) for row in rows]
        finally:
            connection.close()

    def get(self, request_id: str) -> dict[str, object]:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM approval_requests WHERE id=?", (request_id,)
            ).fetchone()
            if row is None:
                raise ValueError("Richiesta di approvazione non trovata")
            return self._decode(row)
        finally:
            connection.close()

    def claim(self, request_id: str, reviewer_email: str) -> dict[str, object]:
        connection = self._connect()
        try:
            cursor = connection.execute(
                """
                UPDATE approval_requests
                SET status='executing', reviewer_email=?, reviewed_at=?
                WHERE id=? AND status='pending' AND execution_enabled=1
                """,
                (reviewer_email.casefold(), datetime.now(UTC).isoformat(), request_id),
            )
            if cursor.rowcount != 1:
                raise ValueError(
                    "La richiesta non è eseguibile o è già stata elaborata"
                )
            connection.commit()
        finally:
            connection.close()
        return self.get(request_id)

    def complete(
        self,
        request_id: str,
        *,
        result: dict[str, object] | None = None,
        error: str | None = None,
    ) -> dict[str, object]:
        status = "completed" if error is None else "failed"
        connection = self._connect()
        try:
            cursor = connection.execute(
                """
                UPDATE approval_requests
                SET status=?, result_json=?, error_message=?
                WHERE id=? AND status='executing'
                """,
                (
                    status,
                    json.dumps(result, ensure_ascii=False, default=str)
                    if result is not None
                    else None,
                    error[:500] if error else None,
                    request_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("Stato della richiesta non valido")
            connection.commit()
        finally:
            connection.close()
        return self.get(request_id)


def notify_approvers(request_id: str, actor: Actor, question: str) -> bool:
    recipients = sorted(approver_emails())
    host = os.environ.get("CHATPSA_SMTP_HOST", "").strip()
    sender = os.environ.get("CHATPSA_SMTP_FROM", "").strip()
    if not recipients or not host or not sender:
        return False
    port = int(os.environ.get("CHATPSA_SMTP_PORT", "587"))
    username = os.environ.get("CHATPSA_SMTP_USERNAME", "").strip()
    password = os.environ.get("CHATPSA_SMTP_PASSWORD", "")
    base_url = os.environ.get("CHATPSA_PUBLIC_URL", "").rstrip("/")
    message = EmailMessage()
    message["Subject"] = f"ChatPSA: approvazione richiesta {request_id[:8]}"
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content(
        "È stata proposta una modifica tramite ChatPSA.\n\n"
        f"Richiedente: {actor.name} <{actor.email}>\n"
        f"Richiesta: {question[:500]}\n"
        f"ID: {request_id}\n"
        + (f"Apri: {base_url}/approvals/{request_id}\n" if base_url else "")
        + "\nLa modifica non è stata applicata e richiede approvazione."
    )
    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=15) as smtp:
        smtp.starttls(context=context)
        if username:
            smtp.login(username, password)
        smtp.send_message(message)
    return True
