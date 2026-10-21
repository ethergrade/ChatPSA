from __future__ import annotations

import unittest

from chatpsa.diagnostics import diagnose_workflow, investigate_ticket


class WorkflowDiagnosticsTests(unittest.TestCase):
    def test_reports_duplicate_actions_and_dangling_step_references(self) -> None:
        workflow = {
            "id": 11,
            "name": "Incident",
            "active": True,
            "steps": [
                {
                    "fdid": 100,
                    "step_id": 1,
                    "name": "Start",
                    "isstart": True,
                    "actions": [
                        {"action_id": 90, "end_step": 999},
                        {"action_id": 90, "end_step": 2},
                    ],
                },
                {
                    "fdid": 200,
                    "step_id": 2,
                    "name": "End",
                    "isend": True,
                    "actions": [],
                },
            ],
        }

        result = diagnose_workflow(workflow)
        codes = {finding["code"] for finding in result["findings"]}

        self.assertIn("duplicate_step_actions", codes)
        self.assertIn("dangling_step_reference", codes)
        self.assertEqual(result["summary"]["start_step_count"], 1)
        self.assertEqual(result["summary"]["end_step_count"], 1)

    def test_ticket_investigation_correlates_configuration(self) -> None:
        result = investigate_ticket(
            {"id": 123, "status_id": 1, "tickettype_id": 2, "workflow_id": 11},
            status={"id": 1, "name": "Open", "statuschangeto": 9},
            tickettype={"id": 2, "name": "Incident", "workflow_id": 12},
            workflow={
                "id": 11,
                "name": "Workflow",
                "active": True,
                "steps": [
                    {
                        "fdid": 100,
                        "step_id": 1,
                        "name": "Start",
                        "isstart": True,
                        "isend": True,
                        "actions": [],
                    }
                ],
            },
        )
        codes = {finding["code"] for finding in result["findings"]}

        self.assertIn("status_auto_transition", codes)
        self.assertIn("workflow_differs_from_type_default", codes)
        self.assertIn("workflow_diagnostics", result)


if __name__ == "__main__":
    unittest.main()
