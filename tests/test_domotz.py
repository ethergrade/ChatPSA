from __future__ import annotations

import json
import unittest

import httpx

from chatpsa.config import Settings
from chatpsa.domotz import DomotzClient, normalize_domotz_base_url


class DomotzTests(unittest.IsolatedAsyncioTestCase):
    async def test_client_uses_api_key_and_safe_projection(self) -> None:
        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path.endswith("/agent"):
                return httpx.Response(
                    200,
                    json=[
                        {
                            "id": 1,
                            "status": {"value": "ONLINE", "last_change": "now", "secret": "drop"},
                            "secret": "drop",
                        }
                    ],
                )
            return httpx.Response(200, json={"alerts": []})

        settings = Settings(
            base_url="https://halo.invalid",
            client_id="id",
            client_secret="secret",
            domotz_api_url="https://domotz.invalid/public-api/v1/agent/99/device",
            domotz_api_key="api-secret",
        )
        async with DomotzClient(settings, transport=httpx.MockTransport(handler)) as client:
            result = await client.overview()

        self.assertEqual(result["summary"]["online_agents"], 1)
        self.assertNotIn("secret", result["agents"][0])
        self.assertEqual(requests[0].headers["x-api-key"], "api-secret")

    def test_normalizes_configured_resource_url(self) -> None:
        result = normalize_domotz_base_url(
            "https://example.invalid/prefix/public-api/v1/agent/42/device"
        )
        self.assertEqual(result, "https://example.invalid/prefix/public-api/v1/")
