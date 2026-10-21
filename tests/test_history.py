from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from chatpsa.history import HistoryStore


class HistoryTests(unittest.TestCase):
    def test_history_is_owner_scoped_and_can_be_renamed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = HistoryStore(Path(directory) / "history.sqlite3")
            created = store.append_exchange(
                owner_email="agent@example.com",
                question="Analizza ticket 42",
                answer="Analisi pronta",
                metadata={"read_only": True},
            )
            self.assertEqual(len(store.list_conversations("agent@example.com")), 1)
            self.assertEqual(store.list_conversations("other@example.com"), [])
            messages = store.get_messages("agent@example.com", created["id"])
            self.assertEqual([item["role"] for item in messages], ["user", "assistant"])
            renamed = store.rename("agent@example.com", created["id"], "Nuovo titolo")
            self.assertEqual(renamed["title"], "Nuovo titolo")

    def test_store_exposes_no_delete_operation(self) -> None:
        self.assertFalse(hasattr(HistoryStore, "delete"))
