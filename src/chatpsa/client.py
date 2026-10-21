"""Async HaloPSA REST client with OAuth refresh and one exact retry on 401."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from typing import Any

import httpx

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

    async def __aenter__(self) -> "HaloClient":
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
            raise RuntimeError("HaloPSA returned an unexpected Agent/me response")
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
            raise RuntimeError("HaloPSA returned an unexpected ticket response")
        return payload
