from __future__ import annotations

import unittest

from chatpsa.safe import (
    safe_outcome_projection,
    safe_status_projection,
    safe_ticket_projection,
    safe_ticketrule_projection,
    safe_tickettype_projection,
    safe_workflow_projection,
)


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

    def test_admin_resource_projections_drop_unknown_and_nested_fields(self) -> None:
        self.assertEqual(
            safe_status_projection(
                {"id": 1, "name": "Open", "unknown": "drop", "nested": {}}
            ),
            {"id": 1, "name": "Open"},
        )
        self.assertEqual(
            safe_tickettype_projection(
                {
                    "id": 2,
                    "name": "Incident",
                    "workflow_id": 11,
                    "access_control": [{"private": True}],
                }
            ),
            {"id": 2, "name": "Incident", "workflow_id": 11},
        )
        self.assertEqual(
            safe_outcome_projection(
                {"id": 3, "buttonname": "Resolve", "fields": [{"private": True}]}
            ),
            {"id": 3, "buttonname": "Resolve"},
        )
        self.assertEqual(
            safe_ticketrule_projection(
                {
                    "id": 4,
                    "name": "Route ticket",
                    "criteria": [
                        {
                            "id": 5,
                            "fieldname": "status_id",
                            "value_int": 1,
                            "private": "drop",
                        }
                    ],
                    "outcomes": [
                        {
                            "id": 6,
                            "fieldname": "new_status_id",
                            "value_type_id": 2,
                            "private": "drop",
                        }
                    ],
                    "access_control": [{"private": True}],
                }
            ),
            {
                "id": 4,
                "name": "Route ticket",
                "criteria": [
                    {"id": 5, "fieldname": "status_id", "value_int": 1}
                ],
                "outcomes": [
                    {
                        "id": 6,
                        "fieldname": "new_status_id",
                        "value_type_id": 2,
                    }
                ],
            },
        )

    def test_workflow_projection_recursively_allowlists_children(self) -> None:
        raw = {
            "id": 11,
            "name": "Workflow",
            "flow_chart_json": "drop",
            "steps": [
                {
                    "fdid": 10,
                    "name": "Start",
                    "private": "drop",
                    "actions": [
                        {
                            "id": 20,
                            "action_id": 30,
                            "action_name": "Continue",
                            "restrictions": [{"private": True}],
                        }
                    ],
                }
            ],
            "stages": [{"id": 40, "name": "Triage", "private": "drop"}],
            "always_allow_actions": [
                {"id": 50, "buttonname": "Report", "private": "drop"}
            ],
            "access_control": [{"private": True}],
        }

        self.assertEqual(
            safe_workflow_projection(raw),
            {
                "id": 11,
                "name": "Workflow",
                "steps": [
                    {
                        "fdid": 10,
                        "name": "Start",
                        "actions": [
                            {
                                "id": 20,
                                "action_id": 30,
                                "action_name": "Continue",
                            }
                        ],
                    }
                ],
                "stages": [{"id": 40, "name": "Triage"}],
                "always_allow_actions": [{"id": 50, "buttonname": "Report"}],
            },
        )


if __name__ == "__main__":
    unittest.main()
