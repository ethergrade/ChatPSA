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

    async def test_read_only_resource_methods_use_expected_endpoints(self) -> None:
        paths: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/auth/token":
                return httpx.Response(
                    200,
                    json={"access_token": "token", "expires_in": 300},
                )
            paths.append(request.url.path)
            if request.url.path in {
                "/api/Status",
                "/api/TicketType",
                "/api/Workflow",
                "/api/Outcome",
                "/api/TicketRules",
            }:
                return httpx.Response(200, json=[{"id": 1}])
            return httpx.Response(200, json={"id": 1})

        settings = Settings(
            base_url="https://example.invalid",
            client_id="id",
            client_secret="secret",
        )
        async with HaloClient(
            settings,
            transport=httpx.MockTransport(handler),
        ) as client:
            await client.list_statuses()
            await client.get_status(1)
            await client.list_ticket_types()
            await client.get_ticket_type(1)
            await client.list_workflows()
            await client.get_workflow(1)
            await client.save_workflow({"id": 0})
            await client.delete_workflow(1)
            await client.list_outcomes()
            await client.get_outcome(1)
            await client.list_ticket_rules()
            await client.get_ticket_rule(1)
            await client.save_ticket_rule({"id": 0})
            await client.delete_ticket_rule(1)

        self.assertEqual(
            paths,
            [
                "/api/Status",
                "/api/Status/1",
                "/api/TicketType",
                "/api/TicketType/1",
                "/api/Workflow",
                "/api/Workflow/1",
                "/api/Workflow",
                "/api/Workflow/1",
                "/api/Outcome",
                "/api/Outcome/1",
                "/api/TicketRules",
                "/api/TicketRules/1",
                "/api/TicketRules",
                "/api/TicketRules/1",
            ],
        )


if __name__ == "__main__":
    unittest.main()
