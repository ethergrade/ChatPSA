"""Internal conversational desk for HaloPSA and Domotz investigations."""

from __future__ import annotations

import os
import re
import hmac
import asyncio
from collections.abc import Mapping
from json import JSONDecodeError, loads
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.datastructures import UploadFile
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .client import HaloClient
from .ai import ImageAttachment, OpenAIAdvisor
from .approvals import (
    Actor,
    ApprovalStore,
    approver_emails,
    is_change_request,
    notify_approvers,
)
from .config import Settings
from .change_control import (
    build_category_payload,
    build_status_payload,
    build_tickettype_payload,
    extract_object_id,
)
from .diagnostics import diagnose_workflow, investigate_ticket
from .domotz import DomotzClient
from .knowledge import load_guides, search_guides, search_tenant_memory
from .kb import build_kb_article_create_plan, build_release_create_plan
from .history import HistoryStore
from .safe import (
    safe_agent_projection,
    safe_category_projection,
    safe_kb_article_projection,
    safe_status_projection,
    safe_release_projection,
    safe_release_type_projection,
    safe_ticketrule_projection,
    safe_tickettype_projection,
)

STATIC_DIR = Path(__file__).with_name("web_static")
MAX_QUESTION_LENGTH = 2_000
MAX_REQUEST_BYTES = 36 * 1024 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGES = 4
ALLOWED_IMAGE_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/webp", "image/gif"}
)
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})
SHARED_AGENT = Actor(
    name="ServiceDesk condiviso",
    email="servicedesk.shared@chatpsa.invalid",
    role="agent",
)
DOMOTZ_TERMS = (
    "domotz",
    "rete",
    "network",
    "device",
    "dispositivo",
    "offline",
    "alert",
)

TICKET_PATTERN = re.compile(r"\b(?:ticket|richiesta)\s*#?\s*(\d+)\b", re.IGNORECASE)
WORKFLOW_PATTERN = re.compile(r"\bworkflow\s*#?\s*(\d+)\b", re.IGNORECASE)
RULE_PATTERN = re.compile(
    r"\b(?:ticket\s*rule|rule|regola)\s*#?\s*(\d+)\b",
    re.IGNORECASE,
)
STATUS_PATTERN = re.compile(r"\b(?:stato|status)\b", re.IGNORECASE)
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _mapped_agent(
    settings: Settings, supplied: str, claimed_email: str
) -> Actor | None:
    """Resolve a personal agent only from a server-side token mapping."""

    if not settings.agent_identities_json or not EMAIL_PATTERN.fullmatch(claimed_email):
        return None
    try:
        configured = loads(settings.agent_identities_json)
    except (JSONDecodeError, TypeError):
        return None
    if not isinstance(configured, Mapping):
        return None
    identity = configured.get(claimed_email.casefold())
    if not isinstance(identity, Mapping):
        return None
    token = str(identity.get("token", ""))
    name = str(identity.get("name", "")).strip()
    email = str(identity.get("email", claimed_email)).strip().casefold()
    if (
        not token
        or not name
        or not EMAIL_PATTERN.fullmatch(email)
        or not hmac.compare_digest(supplied, f"Bearer {token}")
    ):
        return None
    return Actor(name=name[:160], email=email[:254], role="agent")


def _positive_id(value: Any) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


def _match_id(pattern: re.Pattern[str], message: str) -> int | None:
    match = pattern.search(message)
    return int(match.group(1)) if match else None


def _normalise_status_name(value: str) -> str:
    """Make a status name comparable across spaces, punctuation, and case."""

    return "".join(character for character in value.casefold() if character.isalnum())


def _status_query(message: str) -> str | None:
    """Extract the requested status name from a natural-language question."""

    match = STATUS_PATTERN.search(message)
    if not match:
        return None
    remainder = message[match.end() :].strip(" \t\n:,-–—\"'“”")
    remainder = re.sub(
        r"^(?:denominato|chiamato|named|con\s+nome|che\s+si\s+chiama)\b",
        "",
        remainder,
        flags=re.IGNORECASE,
    ).strip(" \t\n:,-–—\"'“”")
    remainder = re.split(
        r"\s+(?:e\s+)?(?:dimmi|cosa\s+fa|che\s+fa|come\s+funziona|quale\b)",
        remainder,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip(" \t\n:,-–—\"'“”?.")
    return remainder


async def _inspect_status(message: str, client: Any) -> dict[str, Any]:
    """Find a tenant Status by name and return its live configuration safely."""

    query = _status_query(message)
    if query is None:
        raise ValueError("La domanda non contiene uno status da cercare")
    statuses = await client.list_statuses()
    query_key = _normalise_status_name(query)
    candidates = [
        status
        for status in statuses
        if isinstance(status.get("name"), str)
        and (
            not query_key
            or query_key in _normalise_status_name(status["name"])
            or _normalise_status_name(status["name"]) in query_key
        )
    ]
    candidate_summaries = [safe_status_projection(status) for status in candidates]

    if not query_key:
        return {
            "mode": "status_list",
            "title": "Status HaloPSA",
            "summary": f"Lettura live di {len(candidate_summaries)} status del tenant.",
            "evidence": [
                {"label": "Status disponibili", "value": len(candidate_summaries)}
            ],
            "findings": [],
            "next_steps": ["Indica il nome dello status da esaminare."],
            "data": {"statuses": candidate_summaries},
            "read_only": True,
        }

    if not candidates:
        return {
            "mode": "status_not_found",
            "title": "Status non trovato",
            "summary": f'Nessuno status del tenant corrisponde a "{query}".',
            "evidence": [
                {"label": "Status esaminati", "value": len(statuses)},
                {"label": "Ricerca", "value": query},
            ],
            "findings": [
                {
                    "severity": "info",
                    "code": "status_not_found",
                    "message": "La ricerca live non ha trovato corrispondenze.",
                }
            ],
            "next_steps": ["Verifica l'ortografia o usa una parte più distintiva del nome."],
            "data": {"query": query, "candidates": []},
            "read_only": True,
        }

    if len(candidates) > 1:
        return {
            "mode": "status_candidates",
            "title": "Status da disambiguare",
            "summary": f'La ricerca live per "{query}" ha trovato {len(candidates)} status.',
            "evidence": [
                {"label": "Ricerca", "value": query},
                {"label": "Corrispondenze", "value": len(candidates)},
            ],
            "findings": [
                {
                    "severity": "info",
                    "code": "status_ambiguous",
                    "message": "Servono più dettagli per identificare un solo status.",
                }
            ],
            "next_steps": ["Indica il nome completo oppure l'ID dello status."],
            "data": {"query": query, "candidates": candidate_summaries},
            "read_only": True,
        }

    status_id = _positive_id(candidates[0].get("id"))
    if status_id is None:
        raise RuntimeError("HaloPSA ha restituito uno status senza ID valido")
    status = await client.get_status(status_id)
    safe_status = safe_status_projection(status)
    target_id = _positive_id(status.get("statuschangeto"))
    target = await client.get_status(target_id) if target_id else None
    safe_target = safe_status_projection(target) if target is not None else None
    findings: list[dict[str, Any]] = []
    if safe_target is not None:
        findings.append(
            {
                "severity": "info",
                "code": "status_auto_transition",
                "message": "Lo status ha una transizione automatica configurata.",
                "target_status_id": target_id,
                "target_status_name": safe_target.get("name"),
                "after_hours": safe_status.get("statuschangetofreq"),
                "use_working_hours": safe_status.get("useworkinghours"),
            }
        )
    return {
        "mode": "status_inspection",
        "title": f"Analisi status {safe_status.get('name', status_id)}",
        "summary": "Status letto in tempo reale dal tenant HaloPSA.",
        "evidence": [
            {"label": "ID", "value": safe_status.get("id")},
            {"label": "Nome", "value": safe_status.get("name")},
            {
                "label": "Transizione automatica",
                "value": safe_target.get("name") if safe_target else None,
            },
            {
                "label": "Ore prima della transizione",
                "value": safe_status.get("statuschangetofreq"),
            },
        ],
        "findings": findings,
        "next_steps": ["Nessuna modifica è stata eseguita."],
        "data": {"query": query, "status": safe_status, "target_status": safe_target},
        "read_only": True,
    }


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
            "Chiedi una procedura per cercare anche nella Knowledge Base HaloPSA.",
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

    if _status_query(normalized) is not None:
        return await _inspect_status(normalized, client)

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
    """Protect the API with host/origin checks and an optional bearer token."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        settings = Settings.from_env()
        allowed_hosts = LOOPBACK_HOSTS | {
            item.strip()
            for item in os.environ.get("CHATPSA_ALLOWED_HOSTS", "").split(",")
            if item.strip()
        }
        host = request.headers.get("host", "").split(":", 1)[0].casefold()
        if host not in {item.casefold() for item in allowed_hosts}:
            return JSONResponse({"error": "Host non consentito."}, status_code=400)

        protected = request.url.path in {"/api/chat", "/api/assist", "/api/guides"} or request.url.path.startswith(("/api/conversations", "/api/approvals"))
        auth_mode = os.environ.get("CHATPSA_AUTH_MODE", "token").strip().casefold()

        if request.url.path in {"/api/chat", "/api/assist"} or (
            request.url.path.startswith("/api/approvals/")
            and request.method == "POST"
        ):
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > MAX_REQUEST_BYTES:
                        return JSONResponse(
                            {"error": "La richiesta è troppo grande."},
                            status_code=413,
                        )
                except ValueError:
                    return JSONResponse(
                        {"error": "Content-Length non valido."}, status_code=400
                    )
            content_type = request.headers.get("content-type", "")
            expected_type = "multipart/form-data" if request.url.path == "/api/assist" else "application/json"
            if content_type.split(";", 1)[0].strip().casefold() != expected_type:
                return JSONResponse(
                    {"error": f"È richiesto un corpo {expected_type}."},
                    status_code=415,
                )

            origin = request.headers.get("origin")
            if origin:
                parsed = urlparse(origin)
                request_port = request.url.port or 80
                origin_port = parsed.port or (443 if parsed.scheme == "https" else 80)
                configured_origins = {
                    item.strip().rstrip("/")
                    for item in os.environ.get(
                        "CHATPSA_ALLOWED_ORIGINS", ""
                    ).split(",")
                    if item.strip()
                }
                same_origin = (
                    parsed.scheme in {"http", "https"}
                    and parsed.hostname in allowed_hosts
                    and origin_port == request_port
                )
                if not same_origin and origin.rstrip("/") not in configured_origins:
                    return JSONResponse(
                        {"error": "Origine della richiesta non consentita."},
                        status_code=403,
                    )

        if protected and auth_mode == "proxy":
            supplied_secret = request.headers.get("x-chatpsa-proxy-secret", "")
            expected_secret = os.environ.get("CHATPSA_PROXY_SHARED_SECRET", "")
            email = request.headers.get("x-forwarded-email", "").strip()
            name = request.headers.get("x-forwarded-user", "").strip() or email
            if (
                not expected_secret
                or not hmac.compare_digest(supplied_secret, expected_secret)
                or not email
            ):
                return JSONResponse(
                    {"error": "Login agente richiesto."}, status_code=401
                )
            role = "approver" if email.casefold() in approver_emails() else "agent"
            request.state.actor = Actor(name=name[:160], email=email[:254], role=role)
        elif protected:
            supplied = request.headers.get("authorization", "")
            requested_role = request.headers.get(
                "x-chatpsa-access-role", "admin"
            ).strip().casefold()
            admin_match = bool(settings.access_token) and hmac.compare_digest(
                supplied, f"Bearer {settings.access_token}"
            )
            agent_match = bool(settings.agent_access_token) and hmac.compare_digest(
                supplied, f"Bearer {settings.agent_access_token}"
            )
            if not settings.access_token and not settings.agent_access_token:
                request.state.actor = Actor(
                    name="Operatore locale",
                    email="local@chatpsa.invalid",
                    role="admin",
                )
            elif requested_role == "agent":
                claimed_email = request.headers.get(
                    "x-chatpsa-agent-email", ""
                ).strip().casefold()
                mapped = _mapped_agent(settings, supplied, claimed_email)
                if mapped is not None:
                    request.state.actor = mapped
                elif agent_match:
                    # A shared role token never authenticates a personal email.
                    # All fallback users share a non-personal history until OIDC
                    # or unique per-agent credentials are configured.
                    request.state.actor = SHARED_AGENT
                else:
                    return JSONResponse(
                        {"error": "Autenticazione agente richiesta."}, status_code=401
                    )
            elif requested_role == "admin" and admin_match:
                name = os.environ.get(
                    "CHATPSA_DEFAULT_AGENT_NAME", "Amministratore locale"
                )[:160]
                email = os.environ.get(
                    "CHATPSA_DEFAULT_AGENT_EMAIL", "admin@chatpsa.invalid"
                )[:254]
                role = (
                    "approver"
                    if email.casefold() in approver_emails()
                    else "admin"
                )
                request.state.actor = Actor(name=name, email=email, role=role)
            else:
                return JSONResponse(
                    {"error": "Autenticazione richiesta."}, status_code=401
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
            "mode": "agent-desk-read-only",
            "writes_enabled": settings.enable_writes,
            "openai_configured": bool(settings.openai_api_key),
            "domotz_configured": bool(
                settings.domotz_api_url and settings.domotz_api_key
            ),
            "model": settings.openai_model,
            "tenant_name": os.environ.get("CHATPSA_TENANT_NAME", "Tenant"),
            "auth_required": bool(
                settings.access_token or settings.agent_access_token
            ),
            "agent_login_available": bool(settings.agent_access_token),
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


async def guides(_: Request) -> JSONResponse:
    return JSONResponse(
        {
            "guides": [guide.public_dict(include_body=False) for guide in load_guides()]
        },
        headers={"Cache-Control": "no-store"},
    )


def _actor(request: Request) -> Actor:
    actor = getattr(request.state, "actor", None)
    if not isinstance(actor, Actor):
        raise ValueError("Identità agente non disponibile")
    return actor


async def conversations(request: Request) -> JSONResponse:
    try:
        actor = _actor(request)
        items = await asyncio.to_thread(
            HistoryStore().list_conversations, actor.email
        )
        return JSONResponse(
            {"conversations": items}, headers={"Cache-Control": "no-store"}
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def conversation_messages(request: Request) -> JSONResponse:
    try:
        actor = _actor(request)
        items = await asyncio.to_thread(
            HistoryStore().get_messages,
            actor.email,
            request.path_params["conversation_id"],
        )
        return JSONResponse(
            {"messages": items}, headers={"Cache-Control": "no-store"}
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)


async def rename_conversation(request: Request) -> JSONResponse:
    try:
        actor = _actor(request)
        body = await request.json()
        title = body.get("title") if isinstance(body, Mapping) else None
        if not isinstance(title, str):
            raise ValueError("Titolo non valido")
        result = await asyncio.to_thread(
            HistoryStore().rename,
            actor.email,
            request.path_params["conversation_id"],
            title,
        )
        return JSONResponse(result, headers={"Cache-Control": "no-store"})
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


def _require_admin(request: Request) -> Actor:
    actor = _actor(request)
    if actor.role not in {"admin", "approver"}:
        raise PermissionError("Accesso amministratore richiesto")
    return actor


async def approval_requests(request: Request) -> JSONResponse:
    try:
        _require_admin(request)
        items = await asyncio.to_thread(ApprovalStore().list_requests)
        return JSONResponse(
            {"requests": items}, headers={"Cache-Control": "no-store"}
        )
    except PermissionError as exc:
        return JSONResponse({"error": str(exc)}, status_code=403)


async def approval_request(request: Request) -> JSONResponse:
    try:
        _require_admin(request)
        item = await asyncio.to_thread(
            ApprovalStore().get, request.path_params["request_id"]
        )
        return JSONResponse(item, headers={"Cache-Control": "no-store"})
    except PermissionError as exc:
        return JSONResponse({"error": str(exc)}, status_code=403)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)


async def approve_request(request: Request) -> JSONResponse:
    store = ApprovalStore()
    try:
        actor = _require_admin(request)
        claimed = await asyncio.to_thread(
            store.claim, request.path_params["request_id"], actor.email
        )
        action_type = claimed.get("action_type")
        payload = claimed.get("payload")
        if not isinstance(payload, Mapping):
            raise ValueError("Payload approvato non valido")
        settings = Settings.from_env()
        async with HaloClient(settings) as client:
            if action_type == "kb_article_create":
                response = await client.save_kb_article(payload)
                object_id = extract_object_id(response)
                persisted = await client.get_kb_article(object_id)
                result: dict[str, object] = {
                    "action": action_type,
                    "verified": True,
                    "article": safe_kb_article_projection(persisted),
                }
            elif action_type == "release_create":
                response = await client.save_release(payload)
                object_id = extract_object_id(response)
                persisted = await client.get_release(object_id)
                result = {
                    "action": action_type,
                    "verified": True,
                    "release": safe_release_projection(persisted),
                }
            elif action_type == "status_create":
                response = await client.save_status(payload)
                object_id = extract_object_id(response)
                persisted = await client.get_status(object_id)
                result = {
                    "action": action_type,
                    "verified": True,
                    "status": safe_status_projection(persisted),
                }
            elif action_type == "tickettype_create":
                response = await client.save_ticket_type(payload)
                object_id = extract_object_id(response)
                persisted = await client.get_ticket_type(object_id)
                result = {
                    "action": action_type,
                    "verified": True,
                    "tickettype": safe_tickettype_projection(persisted),
                }
            elif action_type == "category_create":
                response = await client.save_category(payload)
                object_id = extract_object_id(response)
                persisted = await client.get_category(object_id)
                result = {
                    "action": action_type,
                    "verified": True,
                    "category": safe_category_projection(persisted),
                }
            else:
                raise ValueError("Tipo di azione non eseguibile")
        completed = await asyncio.to_thread(
            store.complete, claimed["id"], result=result
        )
        return JSONResponse(completed, headers={"Cache-Control": "no-store"})
    except PermissionError as exc:
        return JSONResponse({"error": str(exc)}, status_code=403)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception:
        request_id = request.path_params["request_id"]
        try:
            failed = await asyncio.to_thread(
                store.complete,
                request_id,
                error="HaloPSA non ha confermato l'azione approvata.",
            )
        except Exception:
            failed = {"id": request_id, "status": "failed"}
        return JSONResponse(
            {
                "error": "HaloPSA non ha confermato l'azione approvata.",
                "request": failed,
            },
            status_code=502,
        )


def _should_query_halo(message: str) -> bool:
    return any(
        pattern.search(message)
        for pattern in (TICKET_PATTERN, WORKFLOW_PATTERN, RULE_PATTERN, STATUS_PATTERN)
    ) or any(
        term in message.casefold()
        for term in ("connessione halo", "halo api", "halo oauth")
    )


def _execution_actions() -> frozenset[str]:
    return frozenset(
        item.strip()
        for item in os.environ.get(
            "CHATPSA_APPROVAL_EXECUTION_ACTIONS", ""
        ).split(",")
        if item.strip()
    )


def _proposal_title(message: str) -> str:
    candidate = message.split(":", 1)[1] if ":" in message else message
    compact = " ".join(candidate.split())
    return (compact[:177] + "…") if len(compact) > 180 else compact


def _create_name(message: str, resource: str) -> str:
    match = re.search(
        rf"\b(?:crea|creare)\s+(?:un[oa]\s+)?{resource}\s*[:=-]?\s*(.+)$",
        message,
        re.IGNORECASE,
    )
    if not match:
        return _proposal_title(message)
    name = " ".join(match.group(1).split()).strip(" .")
    return name or _proposal_title(message)


def _referenced_id(message: str, pattern: str) -> int | None:
    match = re.search(pattern, message, re.IGNORECASE)
    return int(match.group(1)) if match else None


async def _build_action_proposal(
    message: str, answer: str, settings: Settings
) -> tuple[str | None, dict[str, object], bool]:
    lowered = message.casefold()
    allowed = _execution_actions()
    if re.search(r"\b(?:crea|creare)\s+(?:un[oa]\s+)?status\b", lowered):
        payload = build_status_payload(
            None, {"name": _create_name(message, r"status")}
        )
        return "status_create", payload, "status_create" in allowed

    if re.search(
        r"\b(?:crea|creare)\s+(?:un\s+)?(?:ticket\s*type|tipo\s+ticket)\b",
        lowered,
    ):
        workflow_id = _referenced_id(message, r"\bworkflow\s*#?\s*(\d+)\b")
        status_id = _referenced_id(message, r"\b(?:status|stato)\s*#?\s*(\d+)\b")
        if workflow_id is None or status_id is None:
            return (
                "tickettype_create",
                {
                    "name": _create_name(message, r"(?:ticket\s*type|tipo\s+ticket)"),
                    "missing": [
                        field
                        for field, value in (
                            ("workflow_id", workflow_id),
                            ("initial_status", status_id),
                        )
                        if value is None
                    ],
                },
                False,
            )
        payload = build_tickettype_payload(
            None,
            {
                "name": _create_name(message, r"(?:ticket\s*type|tipo\s+ticket)"),
                "workflow_id": workflow_id,
                "initial_status": status_id,
            },
        )
        return "tickettype_create", payload, "tickettype_create" in allowed

    if re.search(r"\b(?:crea|creare)\s+(?:una\s+)?categori[ae]\b", lowered):
        type_id = _referenced_id(
            message, r"\b(?:ticket\s*type|tipo\s+ticket)\s*#?\s*(\d+)\b"
        )
        if type_id is None:
            return (
                "category_create",
                {
                    "category_name": _create_name(message, r"categori[ae]"),
                    "missing": ["type_id"],
                },
                False,
            )
        name = _create_name(message, r"categori[ae]")
        payload = build_category_payload(
            None,
            {"category_name": name, "level1": name, "type_id": type_id},
        )
        return "category_create", payload, "category_create" in allowed

    if any(
        term in lowered
        for term in (
            "crea kb",
            "crea una kb",
            "creare kb",
            "crea knowledge base",
            "crea articolo",
            "creare articolo",
        )
    ):
        async with HaloClient(settings) as client:
            tags = await client.list_kb_tags()
        combined = f"{message}\n{answer}".casefold()
        selected_ids = [
            tag["id"]
            for tag in tags
            if isinstance(tag.get("id"), int)
            and isinstance(tag.get("text"), str)
            and len(tag["text"].strip()) >= 2
            and tag["text"].strip().casefold() in combined
        ][:20]
        payload = build_kb_article_create_plan(
            title=_proposal_title(message),
            description=message,
            resolution=answer,
            tag_ids=selected_ids,
            available_tags=tags,
        )
        return "kb_article_create", payload, "kb_article_create" in allowed

    if any(term in lowered for term in ("release notes", "release note", "note di rilascio")):
        async with HaloClient(settings) as client:
            release_types = await client.list_release_types()
        match = re.search(
            r"(?:tipo\s+release|release\s+type)\s*#?\s*(\d+)",
            message,
            re.IGNORECASE,
        )
        release_type_id = int(match.group(1)) if match else None
        if release_type_id is None:
            matching_types = [
                item
                for item in release_types
                if isinstance(item.get("name"), str)
                and item["name"].casefold() in lowered
            ]
            if len(matching_types) == 1:
                release_type_id = matching_types[0].get("id")
        if not isinstance(release_type_id, int):
            return (
                "release_create",
                {
                    "name": _proposal_title(message),
                    "note": answer,
                    "available_release_types": [
                        safe_release_type_projection(item) for item in release_types
                    ],
                    "missing": "release_type_id",
                },
                False,
            )
        payload = build_release_create_plan(
            name=_proposal_title(message),
            notes=answer,
            release_type_id=release_type_id,
            available_types=release_types,
        )
        return "release_create", payload, "release_create" in allowed
    return None, {}, False


async def _collect_evidence(message: str, settings: Settings) -> tuple[dict[str, Any], list[dict[str, str]]]:
    evidence: dict[str, Any] = {
        "tenant": os.environ.get("CHATPSA_TENANT_NAME", "Tenant"),
        "tenant_memory": search_tenant_memory(message),
    }
    sources: list[dict[str, str]] = []
    if evidence["tenant_memory"]:
        names = sorted({item["source"] for item in evidence["tenant_memory"]})
        sources.extend({"type": "memoria", "label": name} for name in names)

    if _should_query_halo(message):
        try:
            async with HaloClient(settings) as client:
                evidence["halopsa"] = await answer_question(message, client)
            sources.append({"type": "live", "label": "HaloPSA"})
        except Exception:
            evidence["halopsa"] = {"available": False}

    lowered = message.casefold()
    try:
        async with HaloClient(settings) as client:
            articles = await client.search_kb_articles(message, limit=5)
        safe_articles = [
            safe_kb_article_projection(article) for article in articles
        ]
        if safe_articles:
            evidence["halo_kb"] = safe_articles
            sources.append({"type": "live", "label": "HaloPSA Knowledge Base"})
    except Exception:
        evidence["halo_kb"] = {"available": False}

    if any(term in lowered for term in DOMOTZ_TERMS):
        if settings.domotz_api_url and settings.domotz_api_key:
            try:
                async with DomotzClient(settings) as client:
                    evidence["domotz"] = await client.overview()
                sources.append({"type": "live", "label": "Domotz"})
            except Exception:
                evidence["domotz"] = {"available": False}
        else:
            evidence["domotz"] = {"configured": False}
    return evidence, sources


async def assist(request: Request) -> JSONResponse:
    try:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_REQUEST_BYTES:
            return JSONResponse({"error": "La richiesta è troppo grande."}, status_code=413)
        form = await request.form(max_files=MAX_IMAGES, max_fields=4)
        message = form.get("message")
        conversation_id_raw = form.get("conversation_id")
        conversation_id = (
            conversation_id_raw.strip()
            if isinstance(conversation_id_raw, str) and conversation_id_raw.strip()
            else None
        )
        if not isinstance(message, str) or not message.strip():
            raise ValueError("La domanda non può essere vuota")
        if len(message) > MAX_QUESTION_LENGTH:
            raise ValueError("La domanda è troppo lunga")

        uploads = [item for item in form.getlist("images") if isinstance(item, UploadFile)]
        if len(uploads) > MAX_IMAGES:
            raise ValueError(f"Puoi allegare al massimo {MAX_IMAGES} immagini")
        images: list[ImageAttachment] = []
        for upload in uploads:
            media_type = (upload.content_type or "").casefold()
            if media_type not in ALLOWED_IMAGE_TYPES:
                raise ValueError("Formato immagine non supportato")
            data = await upload.read(MAX_IMAGE_BYTES + 1)
            if len(data) > MAX_IMAGE_BYTES:
                raise ValueError("Ogni immagine deve essere inferiore a 8 MB")
            images.append(
                ImageAttachment(
                    filename=(upload.filename or "immagine")[:160],
                    media_type=media_type,
                    data=data,
                )
            )

        settings = Settings.from_env()
        if not settings.openai_api_key:
            return JSONResponse(
                {"error": "OPENAI_API_KEY non è configurata."}, status_code=503
            )
        relevant_guides = search_guides(message)
        evidence, sources = await _collect_evidence(message, settings)
        sources.extend(
            {"type": "guida", "label": guide.title} for guide in relevant_guides
        )
        if images:
            sources.append(
                {"type": "immagini", "label": f"{len(images)} allegati"}
            )
        async with OpenAIAdvisor(settings) as advisor:
            result = await advisor.analyze(
                message,
                evidence=evidence,
                guides=relevant_guides,
                images=images,
            )
        approval = None
        if is_change_request(message):
            actor = _actor(request)
            action_type, action_payload, execution_enabled = (
                await _build_action_proposal(message, result["answer"], settings)
            )
            approval = await asyncio.to_thread(
                ApprovalStore().create,
                actor=actor,
                question=message,
                proposed_answer=result["answer"],
                sources=sources,
                action_type=action_type,
                payload=action_payload,
                execution_enabled=execution_enabled,
            )
            try:
                approval["email_notified"] = await asyncio.to_thread(
                    notify_approvers, approval["id"], actor, message
                )
            except Exception:
                approval["email_notified"] = False
        actor = _actor(request)
        history_metadata = {
            "mode": "assistenza_ai",
            "title": "Analisi ChatPSA",
            "model": result.get("model"),
            "usage": result.get("usage", {}),
            "sources": sources,
            "approval": approval,
            "read_only": True,
        }
        conversation = await asyncio.to_thread(
            HistoryStore().append_exchange,
            owner_email=actor.email,
            question=message,
            answer=result["answer"],
            metadata=history_metadata,
            conversation_id=conversation_id,
        )
        return JSONResponse(
            {
                "mode": "assistenza_ai",
                "title": "Analisi ChatPSA",
                **result,
                "sources": sources,
                "approval": approval,
                "conversation": conversation,
                "read_only": True,
            },
            headers={"Cache-Control": "no-store"},
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except (httpx.HTTPError, RuntimeError):
        return JSONResponse(
            {"error": "Il servizio AI non ha completato l’analisi."},
            status_code=502,
        )
    except Exception:
        return JSONResponse(
            {"error": "Errore interno durante l’analisi."}, status_code=500
        )
    except Exception:
        return JSONResponse(
            {"error": "Errore interno durante l’indagine."},
            status_code=500,
        )


routes = [
    Route("/", homepage),
    Route("/api/health", health),
    Route("/api/guides", guides),
    Route("/api/conversations", conversations),
    Route("/api/approvals", approval_requests),
    Route("/api/approvals/{request_id:str}", approval_request),
    Route(
        "/api/approvals/{request_id:str}/approve",
        approve_request,
        methods=["POST"],
    ),
    Route(
        "/api/conversations/{conversation_id:str}/messages",
        conversation_messages,
    ),
    Route(
        "/api/conversations/{conversation_id:str}",
        rename_conversation,
        methods=["PATCH"],
    ),
    Route("/api/chat", chat, methods=["POST"]),
    Route("/api/assist", assist, methods=["POST"]),
    Mount("/assets", app=StaticFiles(directory=STATIC_DIR), name="assets"),
]

app = Starlette(debug=False, routes=routes)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(LocalOriginMiddleware)


def main() -> None:
    port_raw = os.environ.get("CHATPSA_WEB_PORT", "8765")
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise RuntimeError("CHATPSA_WEB_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("CHATPSA_WEB_PORT must be between 1 and 65535")
    host = os.environ.get("CHATPSA_WEB_HOST", "127.0.0.1").strip()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
