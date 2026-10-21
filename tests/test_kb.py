from __future__ import annotations

import unittest

from chatpsa.kb import build_kb_article_create_plan
from chatpsa.safe import safe_kb_article_projection


class KnowledgeBaseTests(unittest.TestCase):
    def test_projection_cleans_html_and_drops_unknown_fields(self) -> None:
        projected = safe_kb_article_projection(
            {
                "id": 7,
                "name": "VPN guide",
                "resolution_html": "<p>Restart &amp; verify</p>",
                "secret": "drop",
                "tags": [{"id": 3, "text": "VPN", "private": "drop"}],
            }
        )
        self.assertEqual(projected["resolution_html"], "Restart & verify")
        self.assertNotIn("secret", projected)
        self.assertEqual(projected["tags"], [{"id": 3, "text": "VPN"}])

    def test_create_plan_accepts_only_existing_halo_tags_and_is_inactive(self) -> None:
        plan = build_kb_article_create_plan(
            title="VPN troubleshooting",
            description="The VPN does not connect.",
            resolution="Verify connectivity and restart the client.",
            tag_ids=[3],
            available_tags=[{"id": 3, "text": "VPN", "type": 1}],
        )
        self.assertTrue(plan["inactive"])
        self.assertTrue(plan["is_draft"])
        self.assertEqual(plan["tags"], [{"id": 3, "text": "VPN", "type": 1}])
        with self.assertRaisesRegex(ValueError, "Unknown HaloPSA tag"):
            build_kb_article_create_plan(
                title="VPN troubleshooting",
                description="Problem",
                resolution="Resolution",
                tag_ids=[99],
                available_tags=[{"id": 3, "text": "VPN"}],
            )


if __name__ == "__main__":
    unittest.main()
