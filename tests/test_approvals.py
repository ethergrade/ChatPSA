from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from unittest.mock import patch

from chatpsa.approvals import Actor, ApprovalStore, is_approver, is_change_request


class ApprovalTests(unittest.TestCase):
    def test_change_intent_is_queued_without_execution(self) -> None:
        self.assertTrue(is_change_request("Modifica regola 214"))
        with tempfile.TemporaryDirectory() as directory:
            result = ApprovalStore(Path(directory) / "queue.sqlite3").create(
                actor=Actor("Agent", "agent@example.com"),
                question="Modifica regola 214",
                proposed_answer="Piano non eseguibile",
                sources=[],
            )
            self.assertEqual(result["status"], "pending")
            self.assertTrue((Path(directory) / "queue.sqlite3").is_file())

    def test_agent_cannot_become_approver_by_claiming_an_email(self) -> None:
        with patch.dict(
            "os.environ",
            {"CHATPSA_APPROVER_EMAILS": "approver@example.com"},
        ):
            self.assertFalse(
                is_approver(
                    Actor(
                        "Claimed approver",
                        "approver@example.com",
                        role="agent",
                    )
                )
            )
            self.assertTrue(
                is_approver(
                    Actor(
                        "Verified approver",
                        "approver@example.com",
                        role="approver",
                    )
                )
            )

    def test_executable_request_has_append_only_status_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ApprovalStore(Path(directory) / "queue.sqlite3")
            created = store.create(
                actor=Actor("Agent", "agent@example.com"),
                question="Crea una KB sulla VPN",
                proposed_answer="Bozza",
                sources=[],
                action_type="kb_article_create",
                payload={"name": "VPN", "inactive": True},
                execution_enabled=True,
            )
            self.assertEqual(len(store.list_requests()), 1)
            claimed = store.claim(created["id"], "admin@example.com")
            self.assertEqual(claimed["status"], "executing")
            completed = store.complete(
                created["id"], result={"verified": True, "id": 7}
            )
            self.assertEqual(completed["status"], "completed")
            self.assertTrue(completed["result"]["verified"])
            with self.assertRaisesRegex(ValueError, "già stata elaborata"):
                store.claim(created["id"], "admin@example.com")
