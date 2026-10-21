from __future__ import annotations

import json
import unittest

import httpx

from chatpsa.client import HaloClient
from chatpsa.config import Settings


class ClientRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_401_refreshes_then_retries_identical_request_once(self) -> None:
        token_calls = 0
        api_requests: list[tuple[str, str, bytes]] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal token_calls
            if request.url.path == "/auth/token":
                token_calls += 1
                return httpx.Response(
                    200,
                    json={"access_token": f"token-{token_calls}", "expires_in": 300},
                )

            api_requests.append((request.method, str(request.url), request.content))
            if len(api_requests) == 1:
                return httpx.Response(401, json={"error": "expired"})
            return httpx.Response(200, json={"ok": True})

        settings = Settings(
            base_url="https://example.invalid",
            client_id="id",
            client_secret="secret",
        )
        transport = httpx.MockTransport(handler)
        async with HaloClient(settings, transport=transport) as client:
            result = await client.request(
                "POST",
                "/Example",
                params={"same": "query"},
                json={"same": "body"},
            )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(token_calls, 2)
        self.assertEqual(len(api_requests), 2)
        self.assertEqual(api_requests[0], api_requests[1])
        self.assertEqual(json.loads(api_requests[1][2]), {"same": "body"})


if __name__ == "__main__":
    unittest.main()
