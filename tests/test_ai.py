from __future__ import annotations

import json
import unittest

import httpx

from chatpsa.ai import ImageAttachment, OpenAIAdvisor
from chatpsa.config import Settings


class OpenAIAdvisorTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_selected_model_and_extracts_answer(self) -> None:
        captured: dict[str, object] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            captured["authorization"] = request.headers.get("authorization")
            captured["payload"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "output": [{"content": [{"type": "output_text", "text": "Analisi pronta"}]}],
                    "usage": {"input_tokens": 10, "output_tokens": 3, "total_tokens": 13},
                },
            )

        settings = Settings(
            base_url="https://halo.invalid",
            client_id="id",
            client_secret="secret",
            openai_api_key="openai-secret",
            openai_model="gpt-5.6-sol",
        )
        async with OpenAIAdvisor(settings, transport=httpx.MockTransport(handler)) as advisor:
            result = await advisor.analyze(
                "Cosa vedo?",
                evidence={"safe": True},
                guides=[],
                images=[ImageAttachment("x.png", "image/png", b"png")],
            )

        self.assertEqual(result["answer"], "Analisi pronta")
        self.assertEqual(captured["authorization"], "Bearer openai-secret")
        payload = captured["payload"]
        self.assertEqual(payload["model"], "gpt-5.6-sol")
        self.assertFalse(payload["store"])
        self.assertTrue(payload["input"][0]["content"][1]["image_url"].startswith("data:image/png;base64,"))
        self.assertIn("status_inspection", payload["instructions"])
