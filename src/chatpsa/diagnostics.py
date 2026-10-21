"""Deterministic diagnostics for HaloPSA tickets and workflow configuration."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from .safe import (
    safe_status_projection,
    safe_ticket_projection,
    safe_tickettype_projection,
    safe_workflow_projection,
)


def _positive_int(value: Any) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


def diagnose_workflow(workflow: Mapping[str, Any]) -> dict[str, Any]:
    """Analyze workflow topology without changing the server-side object."""

    raw_steps = workflow.get("steps")
    steps = [step for step in raw_steps if isinstance(step, Mapping)] if isinstance(raw_steps, list) else []
    findings: list[dict[str, Any]] = []

    starts = [step for step in steps if step.get("isstart") is True]
    ends = [
        step
        for step in steps
        if step.get("isend") is True or step.get("islaststep") is True
    ]
    if len(starts) != 1:
        findings.append(
            {
                "severity": "error",
                "code": "workflow_start_count",
                "message": f"Expected exactly one start step; found {len(starts)}.",
            }
        )
    if not ends:
        findings.append(
            {
                "severity": "warning",
                "code": "workflow_no_end",
                "message": "No end or last step is configured.",
            }
        )

    known_step_refs = {
        value
        for step in steps
        for key in ("step_id", "fdid")
        if (value := _positive_int(step.get(key))) is not None
    }
    action_count = 0
    for step in steps:
        raw_actions = step.get("actions")
        actions = (
            [action for action in raw_actions if isinstance(action, Mapping)]
            if isinstance(raw_actions, list)
            else []
        )
        action_count += len(actions)
        if not actions and step not in ends:
            findings.append(
                {
                    "severity": "warning",
                    "code": "step_without_actions",
                    "step_id": step.get("step_id"),
                    "step_name": step.get("name"),
                    "message": "Non-terminal step has no configured actions.",
                }
            )

        action_ids = [
            value
            for action in actions
            if (value := _positive_int(action.get("action_id"))) is not None
        ]
        duplicates = sorted(
            action_id
            for action_id, count in Counter(action_ids).items()
            if count > 1
        )
        if duplicates:
            findings.append(
                {
                    "severity": "warning",
                    "code": "duplicate_step_actions",
                    "step_id": step.get("step_id"),
                    "step_name": step.get("name"),
                    "action_ids": duplicates,
                    "message": "The step contains duplicate configured actions.",
                }
            )

        for action in actions:
            for field in ("start_step", "end_step"):
                reference = _positive_int(action.get(field))
                if reference is not None and reference not in known_step_refs:
                    findings.append(
                        {
                            "severity": "error",
                            "code": "dangling_step_reference",
                            "step_id": step.get("step_id"),
                            "action_id": action.get("action_id"),
                            "reference_field": field,
                            "reference": reference,
                            "message": "Action references a step not present in this workflow.",
                        }
                    )

    if workflow.get("active") is False or workflow.get("notinuse") is True:
        findings.append(
            {
                "severity": "info",
                "code": "workflow_inactive",
                "message": "Workflow is inactive or marked not in use.",
            }
        )

    return {
        "workflow": safe_workflow_projection(workflow),
        "summary": {
            "step_count": len(steps),
            "action_count": action_count,
            "start_step_count": len(starts),
            "end_step_count": len(ends),
            "finding_count": len(findings),
        },
        "findings": findings,
    }


def investigate_ticket(
    ticket: Mapping[str, Any],
    *,
    status: Mapping[str, Any] | None = None,
    tickettype: Mapping[str, Any] | None = None,
    workflow: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Correlate a ticket with its status, ticket type, and workflow."""

    findings: list[dict[str, Any]] = []
    result: dict[str, Any] = {"ticket": safe_ticket_projection(ticket)}

    if status is not None:
        result["status"] = safe_status_projection(status)
        if _positive_int(status.get("statuschangeto")) is not None:
            findings.append(
                {
                    "severity": "info",
                    "code": "status_auto_transition",
                    "message": "Current status has an automatic target status configured.",
                    "target_status_id": status.get("statuschangeto"),
                    "frequency": status.get("statuschangetofreq"),
                }
            )

    if tickettype is not None:
        result["tickettype"] = safe_tickettype_projection(tickettype)
        ticket_workflow = _positive_int(ticket.get("workflow_id"))
        default_workflow = _positive_int(tickettype.get("workflow_id"))
        if ticket_workflow and default_workflow and ticket_workflow != default_workflow:
            findings.append(
                {
                    "severity": "info",
                    "code": "workflow_differs_from_type_default",
                    "message": "Ticket workflow differs from the ticket type default.",
                    "ticket_workflow_id": ticket_workflow,
                    "default_workflow_id": default_workflow,
                }
            )

    if workflow is not None:
        workflow_diagnostics = diagnose_workflow(workflow)
        result["workflow"] = workflow_diagnostics["workflow"]
        result["workflow_diagnostics"] = {
            "summary": workflow_diagnostics["summary"],
            "findings": workflow_diagnostics["findings"],
        }
        current_step = _positive_int(
            ticket.get("workflow_step_id") or ticket.get("workflow_step")
        )
        raw_steps = workflow.get("steps")
        step_items = raw_steps if isinstance(raw_steps, list) else []
        known_refs = {
            value
            for step in step_items
            if isinstance(step, Mapping)
            for key in ("step_id", "fdid")
            if (value := _positive_int(step.get(key))) is not None
        }
        if current_step is not None and current_step not in known_refs:
            findings.append(
                {
                    "severity": "warning",
                    "code": "ticket_workflow_step_missing",
                    "message": "Ticket references a step not present in its workflow.",
                    "workflow_step": current_step,
                }
            )

    result["findings"] = findings
    return result
