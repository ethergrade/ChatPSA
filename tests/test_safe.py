from __future__ import annotations

import unittest

from chatpsa.safe import safe_ticket_projection


class SafeProjectionTests(unittest.TestCase):
    def test_projection_is_deny_by_default_and_drops_nested_values(self) -> None:
        raw = {
            "id": 123,
            "summary": "Allowed",
            "client_name": "Example",
            "agent": {"email": "private@example.invalid"},
            "details": "private details",
            "unknown_future_field": "must not escape",
            "assets": [{"id": 1}, {"id": 2}],
        }

        result = safe_ticket_projection(raw)

        self.assertEqual(
            result,
            {
                "id": 123,
                "summary": "Allowed",
                "client_name": "Example",
                "assets_count": 2,
            },
        )


if __name__ == "__main__":
    unittest.main()
