"""Async HaloPSA REST client with OAuth refresh and one exact retry on 401."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from typing import Any

import httpx
from typing_extensions import Self

from .config import Settings


class HaloClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self._http = httpx.AsyncClient(
            timeout=settings.timeout_seconds,
            follow_redirects=True,
            transport=transport,
        )
        self._access_token: str | None = None
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _token(self, *, force_refresh: bool = False) -> str:
        async with self._token_lock:
            now = time.monotonic()
            if (
                not force_refresh
                and self._access_token
                and now < self._token_expires_at
            ):
                return self._access_token

            response = await self._http.post(
                f"{self.settings.base_url}/auth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.settings.client_id,
                    "client_secret": self.settings.client_secret,
                    "scope": self.settings.scope,
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
            token = payload.get("access_token")
            if not isinstance(token, str) or not token:
                raise RuntimeError("HaloPSA token response did not contain an access token")

            expires_in = payload.get("expires_in", 300)
            try:
                lifetime = max(float(expires_in), 1.0)
            except (TypeError, ValueError):
                lifetime = 300.0
            self._access_token = token
            self._token_expires_at = now + max(lifetime - 30.0, 1.0)
            return token

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        """Perform an API request, refreshing and retrying exactly once on 401."""

        normalized_method = method.upper()
        normalized_path = "/" + path.lstrip("/")
        url = f"{self.settings.base_url}/api{normalized_path}"

        token = await self._token()
        response = await self._http.request(
            normalized_method,
            url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            params=params,
            json=json,
        )
        if response.status_code == 401:
            token = await self._token(force_refresh=True)
            response = await self._http.request(
                normalized_method,
                url,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                params=params,
                json=json,
            )

        response.raise_for_status()
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    async def get_agent_me(self) -> Mapping[str, Any]:
        payload = await self.request("GET", "/Agent/me")
        if not isinstance(payload, Mapping):
            raise TypeError("HaloPSA returned an unexpected Agent/me response")
        return payload

    async def get_ticket(self, ticket_id: int) -> Mapping[str, Any]:
        if ticket_id <= 0:
            raise ValueError("ticket_id must be a positive integer")
        payload = await self.request(
            "GET",
            f"/Tickets/{ticket_id}",
            params={"includedetails": "true"},
        )
        if not isinstance(payload, Mapping):
            raise TypeError("HaloPSA returned an unexpected ticket response")
        return payload

    async def _list_objects(self, path: str, resource_name: str) -> list[Mapping[str, Any]]:
        payload = await self.request("GET", path)
        if not isinstance(payload, list) or not all(
            isinstance(item, Mapping) for item in payload
        ):
            raise RuntimeError(f"HaloPSA returned an unexpected {resource_name} list")
        return payload

    async def _get_object(
        self,
        path: str,
        object_id: int,
        resource_name: str,
    ) -> Mapping[str, Any]:
        if object_id <= 0:
            raise ValueError(f"{resource_name}_id must be a positive integer")
        payload = await self.request("GET", f"{path}/{object_id}")
        if not isinstance(payload, Mapping):
            raise TypeError(f"HaloPSA returned an unexpected {resource_name} response")
        return payload

    async def list_statuses(self) -> list[Mapping[str, Any]]:
        return await self._list_objects("/Status", "status")

    async def get_status(self, status_id: int) -> Mapping[str, Any]:
        return await self._get_object("/Status", status_id, "status")

    async def list_ticket_types(self) -> list[Mapping[str, Any]]:
        return await self._list_objects("/TicketType", "tickettype")

    async def get_ticket_type(self, tickettype_id: int) -> Mapping[str, Any]:
        return await self._get_object("/TicketType", tickettype_id, "tickettype")

    async def save_ticket_type(self, payload: Mapping[str, Any]) -> Any:
        return await self.request("POST", "/TicketType", json=[dict(payload)])

    async def delete_ticket_type(self, tickettype_id: int) -> Any:
        if tickettype_id <= 0:
            raise ValueError("tickettype_id must be a positive integer")
        return await self.request("DELETE", f"/TicketType/{tickettype_id}")

    async def list_categories(self) -> list[Mapping[str, Any]]:
        return await self._list_objects("/Category", "category")

    async def get_category(self, category_id: int) -> Mapping[str, Any]:
        return await self._get_object("/Category", category_id, "category")

    async def save_category(self, payload: Mapping[str, Any]) -> Any:
        return await self.request("POST", "/Category", json=[dict(payload)])

    async def delete_category(self, category_id: int) -> Any:
        if category_id <= 0:
            raise ValueError("category_id must be a positive integer")
        return await self.request("DELETE", f"/Category/{category_id}")

    async def list_workflows(self) -> list[Mapping[str, Any]]:
        return await self._list_objects("/Workflow", "workflow")

    async def get_workflow(self, workflow_id: int) -> Mapping[str, Any]:
        return await self._get_object("/Workflow", workflow_id, "workflow")

    async def save_workflow(self, payload: Mapping[str, Any]) -> Any:
        return await self.request("POST", "/Workflow", json=[dict(payload)])

    async def delete_workflow(self, workflow_id: int) -> Any:
        if workflow_id <= 0:
            raise ValueError("workflow_id must be a positive integer")
        return await self.request("DELETE", f"/Workflow/{workflow_id}")

    async def list_outcomes(self) -> list[Mapping[str, Any]]:
        return await self._list_objects("/Outcome", "outcome")

    async def get_outcome(self, outcome_id: int) -> Mapping[str, Any]:
        return await self._get_object("/Outcome", outcome_id, "outcome")

    async def list_ticket_rules(self) -> list[Mapping[str, Any]]:
        return await self._list_objects("/TicketRules", "ticketrule")

    async def get_ticket_rule(self, ticketrule_id: int) -> Mapping[str, Any]:
        if ticketrule_id <= 0:
            raise ValueError("ticketrule_id must be a positive integer")
        payload = await self.request(
            "GET",
            f"/TicketRules/{ticketrule_id}",
            params={"includedetails": "true"},
        )
        if not isinstance(payload, Mapping):
            raise TypeError("HaloPSA returned an unexpected ticketrule response")
        return payload

    async def search_kb_articles(
        self, query: str, *, limit: int = 8
    ) -> list[Mapping[str, Any]]:
        query = " ".join(query.split())
        if not query:
            raise ValueError("query must not be empty")
        if not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")
        payload = await self.request(
            "GET",
            "/KBArticle",
            params={
                "search": query,
                "includeactive": "true",
                "pageinate": "true",
                "page_no": 1,
                "page_size": limit,
            },
        )
        if not isinstance(payload, Mapping) or not isinstance(
            payload.get("articles"), list
        ):
            raise RuntimeError("HaloPSA returned an unexpected KB article list")
        return [
            item for item in payload["articles"] if isinstance(item, Mapping)
        ]

    async def get_kb_article(self, article_id: int) -> Mapping[str, Any]:
        return await self._get_object("/KBArticle", article_id, "kb_article")

    async def list_kb_tags(self) -> list[Mapping[str, Any]]:
        return await self._list_objects("/Tags", "tag")

    async def save_kb_article(self, payload: Mapping[str, Any]) -> Any:
        return await self.request("POST", "/KBArticle", json=[dict(payload)])

    async def list_release_types(self) -> list[Mapping[str, Any]]:
        return await self._list_objects("/ReleaseType", "release_type")

    async def get_release(self, release_id: int) -> Mapping[str, Any]:
        return await self._get_object("/Release", release_id, "release")

    async def save_release(self, payload: Mapping[str, Any]) -> Any:
        return await self.request("POST", "/Release", json=[dict(payload)])

    async def save_ticket_rule(self, payload: Mapping[str, Any]) -> Any:
        return await self.request("POST", "/TicketRules", json=[dict(payload)])

    async def delete_ticket_rule(self, ticketrule_id: int) -> Any:
        if ticketrule_id <= 0:
            raise ValueError("ticketrule_id must be a positive integer")
        return await self.request("DELETE", f"/TicketRules/{ticketrule_id}")

    async def save_status(self, payload: Mapping[str, Any]) -> Any:
        return await self.request("POST", "/Status", json=[dict(payload)])

    async def delete_status(self, status_id: int) -> Any:
        if status_id <= 0:
            raise ValueError("status_id must be a positive integer")
        return await self.request("DELETE", f"/Status/{status_id}")
