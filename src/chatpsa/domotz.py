"""Secret-safe, read-only Domotz Public API client."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from .config import Settings

AGENT_FIELDS = (
    "id",
    "display_name",
    "status",
    "timezone",
    "version",
    "creation_time",
)
ALERT_FIELDS = (
    "id",
    "alert_rule_id",
    "collector_id",
    "device_id",
    "severity",
    "status",
    "trigger_condition_repr",
    "trigger_value",
    "triggered_at",
    "closed_at",
    "duration_seconds",
)
DEVICE_FIELDS = (
    "id",
    "display_name",
    "name",
    "status",
    "ip_address",
    "mac",
    "vendor",
    "model",
    "operating_system",
    "protocol",
    "importance",
    "monitoring_state",
)


def normalize_domotz_base_url(configured_url: str) -> str:
    parts = urlsplit(configured_url)
    marker = "/public-api/v1/"
    if parts.scheme != "https" or not parts.netloc or marker not in parts.path:
        raise ValueError("DOMOTZ_API_URL must identify a Domotz Public API v1 URL")
    prefix = parts.path.split(marker, 1)[0] + marker
    return urlunsplit((parts.scheme, parts.netloc, prefix, "", ""))


def _safe_projection(source: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(source, dict):
        return {}
    return {
        field: source[field]
        for field in fields
        if field in source
        and (
            source[field] is None
            or isinstance(source[field], (str, int, float, bool))
        )
    }


def _safe_agent_projection(source: Any) -> dict[str, Any]:
    result = _safe_projection(source, AGENT_FIELDS)
    if isinstance(source, dict) and isinstance(source.get("status"), dict):
        status = source["status"]
        if isinstance(status.get("value"), str):
            result["status"] = status["value"]
        if isinstance(status.get("last_change"), str):
            result["status_changed_at"] = status["last_change"]
    return result


class DomotzClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not settings.domotz_api_url or not settings.domotz_api_key:
            raise RuntimeError("Domotz is not configured")
        self._http = httpx.AsyncClient(
            base_url=normalize_domotz_base_url(settings.domotz_api_url),
            headers={
                "X-Api-Key": settings.domotz_api_key,
                "Accept": "application/json",
            },
            timeout=settings.timeout_seconds,
            follow_redirects=False,
            transport=transport,
        )

    async def __aenter__(self) -> "DomotzClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._http.aclose()

    async def _get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        if path.startswith(("/", "http:" , "https:")) or ".." in path:
            raise ValueError("Domotz request path must be relative")
        response = await self._http.get(path, params=params)
        response.raise_for_status()
        return response.json()

    async def list_agents(self, *, page_size: int = 50) -> list[dict[str, Any]]:
        payload = await self._get("agent", params={"page_size": min(page_size, 100)})
        if not isinstance(payload, list):
            raise TypeError("Domotz returned an unexpected agent response")
        return [_safe_agent_projection(item) for item in payload]

    async def list_open_alerts(self, *, hours: int = 24) -> list[dict[str, Any]]:
        bounded_hours = max(1, min(hours, 168))
        end = datetime.now(UTC)
        start = end - timedelta(hours=bounded_hours)
        payload = await self._get(
            "alert",
            params={
                "from": start.isoformat().replace("+00:00", "Z"),
                "to": end.isoformat().replace("+00:00", "Z"),
                "status": "Open",
                "page_size": 100,
            },
        )
        items = payload.get("alerts") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise TypeError("Domotz returned an unexpected alert response")
        return [_safe_projection(item, ALERT_FIELDS) for item in items]

    async def get_device(self, agent_id: int, device_id: int) -> dict[str, Any]:
        if agent_id <= 0 or device_id <= 0:
            raise ValueError("Domotz agent and device IDs must be positive")
        payload = await self._get(f"agent/{agent_id}/device/{device_id}")
        return _safe_projection(payload, DEVICE_FIELDS)

    async def overview(self) -> dict[str, Any]:
        agents = await self.list_agents()
        alerts = await self.list_open_alerts()
        return {
            "agents": agents,
            "open_alerts": alerts,
            "summary": {
                "agent_count": len(agents),
                "online_agents": sum(
                    str(agent.get("status", "")).casefold() == "online"
                    for agent in agents
                ),
                "open_alert_count": len(alerts),
            },
        }
