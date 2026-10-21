from __future__ import annotations

import unittest

from mcp.server.mcpserver.exceptions import ToolError

from chatpsa.change_control import (
    STATUS_WRITE_FIELDS,
    authorize_write,
    build_isolated_ticketrule_payload,
    build_isolated_workflow_payload,
    build_scalar_change_plan,
    build_status_payload,
    extract_object_id,
    requested_diff,
    validate_scalar_changes,
)
from chatpsa.config import Settings


class ChangeControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.disabled = Settings(
            base_url="https://example.invalid",
            client_id="id",
            client_secret="secret",
            enable_writes=False,
        )
        self.enabled = Settings(
            base_url="https://example.invalid",
            client_id="id",
            client_secret="secret",
            enable_writes=True,
        )

    def test_unknown_write_fields_are_rejected(self) -> None:
        with self.assertRaisesRegex(ToolError, "non-writable"):
            validate_scalar_changes(
                {"name": "Valid", "unexpected": "drop"},
                allowed_fields=STATUS_WRITE_FIELDS,
            )

    def test_status_create_requires_name(self) -> None:
        with self.assertRaisesRegex(ToolError, "Missing required fields"):
            build_status_payload(None, {"colour": "#000000"})

    def test_status_update_preserves_allowlisted_snapshot(self) -> None:
        result = build_status_payload(
            {
                "id": 7,
                "name": "Open",
                "colour": "#000000",
                "server_only": "drop",
            },
            {"colour": "#ffffff"},
        )
        self.assertEqual(result["id"], 7)
        self.assertEqual(result["name"], "Open")
        self.assertEqual(result["colour"], "#ffffff")
        self.assertNotIn("server_only", result)

    def test_execution_requires_enablement_and_exact_confirmation(self) -> None:
        authorize_write(
            self.disabled,
            dry_run=True,
            confirmation="",
            expected_confirmation="UPDATE STATUS 7",
        )
        with self.assertRaisesRegex(ToolError, "Writes are disabled"):
            authorize_write(
                self.disabled,
                dry_run=False,
                confirmation="UPDATE STATUS 7",
                expected_confirmation="UPDATE STATUS 7",
            )
        with self.assertRaisesRegex(ToolError, "Confirmation mismatch"):
            authorize_write(
                self.enabled,
                dry_run=False,
                confirmation="yes",
                expected_confirmation="UPDATE STATUS 7",
            )
        authorize_write(
            self.enabled,
            dry_run=False,
            confirmation="UPDATE STATUS 7",
            expected_confirmation="UPDATE STATUS 7",
        )

    def test_readback_helpers_report_persisted_values(self) -> None:
        self.assertEqual(extract_object_id([{"id": 8}]), 8)
        self.assertEqual(
            requested_diff(
                {"colour": "#000000"},
                {"colour": "#ffffff"},
                {"colour": "#ffffff"},
            ),
            [
                {
                    "field": "colour",
                    "before": "#000000",
                    "requested": "#ffffff",
                    "persisted": "#ffffff",
                    "matches_requested": True,
                }
            ],
        )

    def test_isolated_workflow_is_inactive_and_has_start_step(self) -> None:
        payload = build_isolated_workflow_payload(
            None,
            {"name": "ChatPSA TEMP VALIDATION unit-workflow", "active": True},
        )
        self.assertFalse(payload["active"])
        self.assertTrue(payload["notinuse"])
        self.assertTrue(payload["steps"][0]["isstart"])

    def test_isolated_workflow_rejects_non_temporary_name(self) -> None:
        with self.assertRaisesRegex(ToolError, "must start"):
            build_isolated_workflow_payload(None, {"name": "Production"})

    def test_isolated_ticketrule_is_inactive_and_strict(self) -> None:
        payload = build_isolated_ticketrule_payload(
            None,
            {
                "name": "ChatPSA TEMP VALIDATION unit-rule",
                "active": True,
                "criteria": [
                    {
                        "fieldname": "requesttypenew",
                        "tablename": "faults",
                        "value_type": "int",
                        "value_int": 999999,
                        "type": 0,
                        "partialmatch": False,
                    }
                ],
            },
        )
        self.assertFalse(payload["active"])
        self.assertEqual(payload["new_status_id"], -1)
        self.assertEqual(payload["criteria"][0]["value_int"], 999999)

        with self.assertRaisesRegex(ToolError, "criteria fields"):
            build_isolated_ticketrule_payload(
                None,
                {
                    "name": "ChatPSA TEMP VALIDATION invalid-rule",
                    "criteria": [{"raw": {"nested": "value"}}],
                },
            )

    def test_scalar_change_plan_does_not_mutate_snapshot(self) -> None:
        current = {"id": 11, "name": "Existing", "note": "Before"}
        validated, projected, diff = build_scalar_change_plan(
            current,
            {"note": "After"},
            allowed_fields=frozenset({"name", "note"}),
        )
        self.assertEqual(current["note"], "Before")
        self.assertEqual(validated, {"note": "After"})
        self.assertEqual(projected["note"], "After")
        self.assertTrue(diff[0]["matches_requested"])

        with self.assertRaisesRegex(ToolError, "non-writable"):
            build_scalar_change_plan(
                current,
                {"steps": []},
                allowed_fields=frozenset({"name", "note"}),
            )


if __name__ == "__main__":
    unittest.main()
