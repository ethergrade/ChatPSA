from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from unittest.mock import patch

from chatpsa.knowledge import load_guides, search_guides


class KnowledgeTests(unittest.TestCase):
    def test_load_and_rank_guides(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.md").write_text(
                "---\nid: a\ntitle: Domotz offline\nsummary: Analisi rete\n"
                "tags: domotz, offline\n---\nControlla gli alert.",
                encoding="utf-8",
            )
            guides = load_guides(root)
        self.assertEqual(guides[0].guide_id, "a")

        ranked = search_guides("device Domotz offline")
        self.assertTrue(ranked)
        self.assertEqual(ranked[0].guide_id, "domotz-halo-correlation")

    def test_private_tenant_guides_are_not_loaded_as_full_guides(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "private.md").write_text(
                "---\nid: private\ntitle: Secret workflow\n---\n"
                "OPENAI_API_KEY=must-not-leave",
                encoding="utf-8",
            )
            with patch("chatpsa.knowledge.TENANT_GUIDES_DIR", root):
                guide_ids = {guide.guide_id for guide in load_guides()}

        self.assertNotIn("private", guide_ids)
