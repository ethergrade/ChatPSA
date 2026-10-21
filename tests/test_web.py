from __future__ import annotations

import unittest
from typing import Any

from starlette.testclient import TestClient

from chatpsa.web import MAX_REQUEST_BYTES, answer_question, app


class FakeHaloClient:
    async def get_agent_me(self) -> dict[str, Any]:
        return {"id": 1, "name": "Application Identity", "secret": "drop"}

    async def get_ticket(self, ticket_id: int) -> dict[str, Any]:
        return {
            "id": ticket_id,
            "summary": "Example",
            "status_id": 1,
            "status_name": "Open",
            "tickettype_id": 2,
            "tickettype_name": "Incident",
            "workflow_id": 11,
            "workflow_name": "Incident Management",
            "raw_private": {"password": "drop"},
        }

    async def get_status(self, status_id: int) -> dict[str, Any]:
        return {"id": status_id, "name": "Open", "statuschangeto": 9}

    async def get_ticket_type(self, tickettype_id: int) -> dict[str, Any]:
        return {"id": tickettype_id, "name": "Incident", "workflow_id": 11}

    async def get_workflow(self, workflow_id: int) -> dict[str, Any]:
        return {
            "id": workflow_id,
            "name": "Incident Management",
            "active": True,
            "steps": [
                {
                    "fdid": 10,
                    "step_id": 1,
                    "name": "Start",
                    "isstart": True,
                    "isend": True,
                    "actions": [],
                }
            ],
        }

    async def get_ticket_rule(self, rule_id: int) -> dict[str, Any]:
        return {
            "id": rule_id,
            "name": "Example rule",
            "active": False,
            "precedence": 10,
            "criteria": [{"fieldname": "requesttypenew", "value_int": 2}],
            "outcomes": [],
            "secret": "drop",
        }


class WebQuestionTests(unittest.IsolatedAsyncioTestCase):
    async def test_ticket_question_returns_safe_guided_investigation(self) -> None:
        result = await answer_question("Analizza ticket 123", FakeHaloClient())

        self.assertEqual(result["mode"], "ticket_investigation")
        self.assertTrue(result["read_only"])
        self.assertEqual(result["data"]["ticket"]["id"], 123)
        self.assertNotIn("raw_private", result["data"]["ticket"])
        self.assertTrue(result["findings"])

    async def test_workflow_and_rule_questions_are_routed(self) -> None:
        workflow = await answer_question(
            "Diagnostica workflow 11",
            FakeHaloClient(),
        )
        rule = await answer_question("Controlla regola 214", FakeHaloClient())

        self.assertEqual(workflow["mode"], "workflow_diagnosis")
        self.assertEqual(rule["mode"], "ticket_rule_inspection")
        self.assertNotIn("secret", rule["data"])

    async def test_connection_and_help_questions(self) -> None:
        connection = await answer_question(
            "Verifica connessione OAuth",
            FakeHaloClient(),
        )
        help_result = await answer_question("Cosa puoi fare?", FakeHaloClient())

        self.assertEqual(connection["mode"], "connection")
        self.assertEqual(help_result["mode"], "guide")

    async def test_invalid_question_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "vuota"):
            await answer_question(" ", FakeHaloClient())


class WebSecurityTests(unittest.TestCase):
    def test_rejects_untrusted_host_and_origin(self) -> None:
        with TestClient(app, base_url="http://127.0.0.1:8765") as client:
            invalid_host = client.get(
                "/api/health",
                headers={"Host": "attacker.example"},
            )
            self.assertEqual(invalid_host.status_code, 400)

            invalid_origin = client.post(
                "/api/chat",
                json={"message": "Cosa puoi fare?"},
                headers={"Origin": "https://attacker.example"},
            )
            self.assertEqual(invalid_origin.status_code, 403)

    def test_rejects_non_json_and_oversized_requests(self) -> None:
        with TestClient(app, base_url="http://127.0.0.1:8765") as client:
            wrong_type = client.post(
                "/api/chat",
                content="message=help",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            self.assertEqual(wrong_type.status_code, 415)

            oversized = client.post(
                "/api/chat",
                content=b'{"message":"' + (b"x" * MAX_REQUEST_BYTES) + b'"}',
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(oversized.status_code, 413)

    def test_sends_defensive_browser_headers(self) -> None:
        with TestClient(app, base_url="http://127.0.0.1:8765") as client:
            response = client.get("/")
            self.assertEqual(response.status_code, 200)
            self.assertIn(
                "frame-ancestors 'none'",
                response.headers["content-security-policy"],
            )
            self.assertEqual(response.headers["x-content-type-options"], "nosniff")


if __name__ == "__main__":
    unittest.main()
