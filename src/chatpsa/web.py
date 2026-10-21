"""Local-only conversational web interface for guided HaloPSA investigations."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from json import JSONDecodeError, loads
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .client import HaloClient
from .config import Settings
from .diagnostics import diagnose_workflow, investigate_ticket
from .safe import (
    safe_agent_projection,
    safe_ticketrule_projection,
)

STATIC_DIR = Path(__file__).with_name("web_static")
MAX_QUESTION_LENGTH = 2_000
MAX_REQUEST_BYTES = 8_192
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})

TICKET_PATTERN = re.compile(r"\b(?:ticket|richiesta)\s*#?\s*(\d+)\b", re.IGNORECASE)
WORKFLOW_PATTERN = re.compile(r"\bworkflow\s*#?\s*(\d+)\b", re.IGNORECASE)
RULE_PATTERN = re.compile(
    r"\b(?:ticket\s*rule|rule|regola)\s*#?\s*(\d+)\b",
    re.IGNORECASE,
)


def _positive_id(value: Any) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


def _match_id(pattern: re.Pattern[str], message: str) -> int | None:
    match = pattern.search(message)
    return int(match.group(1)) if match else None


def _finding_summary(findings: list[Mapping[str, Any]]) -> str:
    if not findings:
        return "Non sono emerse anomalie dalle verifiche disponibili."
    errors = sum(item.get("severity") == "error" for item in findings)
    warnings = sum(item.get("severity") == "warning" for item in findings)
    return f"Rilevati {errors} errori e {warnings} avvisi da approfondire."


def _help_response() -> dict[str, Any]:
    return {
        "mode": "guide",
        "title": "Come posso aiutarti con HaloPSA",
        "summary": (
            "Posso analizzare ticket, workflow e Ticket Rules con dati letti "
            "in tempo reale e filtrati da allowlist di sicurezza."
        ),
        "evidence": [],
        "findings": [],
        "next_steps": [
            "Scrivi “Analizza ticket 12345” per ricostruire configurazione e processo.",
            "Scrivi “Diagnostica workflow 11” per controllarne la struttura.",
            "Scrivi “Controlla regola 214” per esaminarne criteri e risultati.",
            "Scrivi “Verifica connessione” per controllare OAuth e API.",
        ],
        "read_only": True,
    }


async def answer_question(message: str, client: Any) -> dict[str, Any]:
    """Route a natural-language question to a safe deterministic investigation."""

    normalized = message.strip()
    if not normalized:
        raise ValueError("La domanda non può essere vuota")
    if len(normalized) > MAX_QUESTION_LENGTH:
        raise ValueError("La domanda è troppo lunga")

    ticket_id = _match_id(TICKET_PATTERN, normalized)
    if ticket_id is not None:
        ticket = await client.get_ticket(ticket_id)
        status_id = _positive_id(ticket.get("status_id"))
        tickettype_id = _positive_id(ticket.get("tickettype_id"))
        workflow_id = _positive_id(ticket.get("workflow_id"))
        status = await client.get_status(status_id) if status_id else None
        tickettype = (
            await client.get_ticket_type(tickettype_id) if tickettype_id else None
        )
        workflow = await client.get_workflow(workflow_id) if workflow_id else None
        investigation = investigate_ticket(
            ticket,
            status=status,
            tickettype=tickettype,
            workflow=workflow,
        )
        findings = list(investigation.get("findings", []))
        workflow_diagnostics = investigation.get("workflow_diagnostics")
        if isinstance(workflow_diagnostics, Mapping):
            nested_findings = workflow_diagnostics.get("findings")
            if isinstance(nested_findings, list):
                findings.extend(
                    item for item in nested_findings if isinstance(item, Mapping)
                )
        safe_ticket = investigation["ticket"]
        evidence = [
            {"label": "Ticket", "value": safe_ticket.get("id")},
            {"label": "Stato", "value": safe_ticket.get("status_name")},
            {"label": "Tipo", "value": safe_ticket.get("tickettype_name")},
            {"label": "Workflow", "value": safe_ticket.get("workflow_name")},
        ]
        return {
            "mode": "ticket_investigation",
            "title": f"Indagine ticket {ticket_id}",
            "summary": _finding_summary(findings),
            "evidence": [item for item in evidence if item["value"] is not None],
            "findings": findings,
            "next_steps": [
                "Verifica gli avvisi evidenziati prima di modificare il processo.",
                "Chiedi il Workflow o la Rule specifica per approfondire.",
            ],
            "data": investigation,
            "read_only": True,
        }

    workflow_id = _match_id(WORKFLOW_PATTERN, normalized)
    if workflow_id is not None:
        workflow = await client.get_workflow(workflow_id)
        diagnostics = diagnose_workflow(workflow)
        summary = diagnostics["summary"]
        return {
            "mode": "workflow_diagnosis",
            "title": f"Diagnostica workflow {workflow_id}",
            "summary": _finding_summary(diagnostics["findings"]),
            "evidence": [
                {"label": "Step", "value": summary["step_count"]},
                {"label": "Azioni", "value": summary["action_count"]},
                {"label": "Evidenze", "value": summary["finding_count"]},
            ],
            "findings": diagnostics["findings"],
            "next_steps": [
                "Controlla transizioni, azioni duplicate e step terminali.",
                "Usa il change plan prima di proporre modifiche ai metadata.",
            ],
            "data": diagnostics,
            "read_only": True,
        }

    rule_id = _match_id(RULE_PATTERN, normalized)
    if rule_id is not None:
        rule = await client.get_ticket_rule(rule_id)
        safe_rule = safe_ticketrule_projection(rule)
        criteria = safe_rule.get("criteria", [])
        outcomes = safe_rule.get("outcomes", [])
        findings: list[dict[str, Any]] = []
        if safe_rule.get("active") is False:
            findings.append(
                {
                    "severity": "info",
                    "code": "rule_inactive",
                    "message": "La regola è inattiva.",
                }
            )
        if not criteria:
            findings.append(
                {
                    "severity": "warning",
                    "code": "rule_without_criteria",
                    "message": "La regola non espone criteri nella lettura corrente.",
                }
            )
        return {
            "mode": "ticket_rule_inspection",
            "title": f"Analisi Ticket Rule {rule_id}",
            "summary": _finding_summary(findings),
            "evidence": [
                {"label": "Attiva", "value": safe_rule.get("active")},
                {"label": "Precedenza", "value": safe_rule.get("precedence")},
                {"label": "Criteri", "value": len(criteria)},
                {"label": "Outcome", "value": len(outcomes)},
            ],
            "findings": findings,
            "next_steps": [
                "Verifica che criteri e outcome corrispondano al processo atteso.",
                "Prepara un change plan prima di modificare la regola.",
            ],
            "data": safe_rule,
            "read_only": True,
        }

    lowered = normalized.casefold()
    if any(
        term in lowered
        for term in ("connessione", "connection", "collegato", "oauth", "api")
    ):
        agent = await client.get_agent_me()
        return {
            "mode": "connection",
            "title": "Connessione HaloPSA",
            "summary": "OAuth e API HaloPSA rispondono correttamente.",
            "evidence": [
                {"label": "Connesso", "value": True},
                {"label": "Identità", "value": safe_agent_projection(agent).get("name")},
            ],
            "findings": [],
            "next_steps": ["Puoi avviare un’indagine su ticket, workflow o regole."],
            "read_only": True,
        }

    return _help_response()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Any) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        return response


class LocalOriginMiddleware(BaseHTTPMiddleware):
    """Reject browser writes to the local API when they originate elsewhere."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if request.url.path == "/api/chat":
            content_type = request.headers.get("content-type", "")
            if content_type.split(";", 1)[0].strip().casefold() != "application/json":
                return JSONResponse(
                    {"error": "È richiesto un corpo JSON."},
                    status_code=415,
                )

            origin = request.headers.get("origin")
            if origin:
                parsed = urlparse(origin)
                request_port = request.url.port or 80
                origin_port = parsed.port or (443 if parsed.scheme == "https" else 80)
                if (
                    parsed.scheme not in {"http", "https"}
                    or parsed.hostname not in LOOPBACK_HOSTS
                    or origin_port != request_port
                ):
                    return JSONResponse(
                        {"error": "Origine della richiesta non consentita."},
                        status_code=403,
                    )
        return await call_next(request)


async def homepage(_: Request) -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


async def health(_: Request) -> JSONResponse:
    settings = Settings.from_env()
    return JSONResponse(
        {
            "ok": True,
            "service": "ChatPSA open",
            "mode": "local-read-only",
            "writes_enabled": settings.enable_writes,
        },
        headers={"Cache-Control": "no-store"},
    )


async def chat(request: Request) -> JSONResponse:
    try:
        raw_body = await request.body()
        if len(raw_body) > MAX_REQUEST_BYTES:
            return JSONResponse(
                {"error": "La richiesta è troppo grande."},
                status_code=413,
            )
        try:
            body = loads(raw_body)
        except (JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("Il corpo della richiesta non è JSON valido") from exc
        if not isinstance(body, Mapping):
            raise ValueError("Il corpo della richiesta deve essere un oggetto JSON")
        message = body.get("message")
        if not isinstance(message, str):
            raise ValueError("Il campo message deve essere una stringa")
        settings = Settings.from_env()
        async with HaloClient(settings) as client:
            response = await answer_question(message, client)
        return JSONResponse(response, headers={"Cache-Control": "no-store"})
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        return JSONResponse(
            {
                "error": "HaloPSA non ha completato la richiesta.",
                "status": status,
            },
            status_code=502,
        )
    except Exception:
        return JSONResponse(
            {"error": "Errore interno durante l’indagine."},
            status_code=500,
        )


routes = [
    Route("/", homepage),
    Route("/api/health", health),
    Route("/api/chat", chat, methods=["POST"]),
    Mount("/assets", app=StaticFiles(directory=STATIC_DIR), name="assets"),
]

app = Starlette(debug=False, routes=routes)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(LocalOriginMiddleware)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["127.0.0.1", "localhost"],
    www_redirect=False,
)


def main() -> None:
    port_raw = os.environ.get("CHATPSA_WEB_PORT", "8765")
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise RuntimeError("CHATPSA_WEB_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("CHATPSA_WEB_PORT must be between 1 and 65535")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
