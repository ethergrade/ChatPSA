"""Validate temporary Workflow and Ticket Rule CRUD without exposing tenant data."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable

import httpx

from chatpsa.change_control import (
    TEMPORARY_OBJECT_PREFIX,
    build_isolated_ticketrule_payload,
    build_isolated_workflow_payload,
    extract_object_id,
    requested_diff,
)
from chatpsa.client import HaloClient
from chatpsa.config import Settings

CONFIRMATION = "CREATE UPDATE DELETE TEMPORARY CHATPSA OBJECTS"


async def _verified_delete(
    delete: Callable[[int], Awaitable[Any]],
    get: Callable[[int], Awaitable[Any]],
    object_id: int,
) -> bool:
    await delete(object_id)
    try:
        await get(object_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return True
        raise
    return False


async def run(confirmation: str) -> dict[str, Any]:
    if confirmation != CONFIRMATION:
        raise RuntimeError(f"Confirmation must be exactly: {CONFIRMATION}")
    settings = Settings.from_env()
    if not settings.enable_writes:
        raise RuntimeError(
            "CHATPSA_ENABLE_WRITES must be true for this live validation"
        )

    suffix = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    workflow_name = f"{TEMPORARY_OBJECT_PREFIX}{suffix} WORKFLOW"
    rule_name = f"{TEMPORARY_OBJECT_PREFIX}{suffix} RULE"
    workflow_id: int | None = None
    rule_id: int | None = None
    result: dict[str, Any] = {
        "workflow": {"created": False, "updated": False, "deleted": False},
        "ticket_rule": {"created": False, "updated": False, "deleted": False},
    }

    async with HaloClient(settings) as client:
        try:
            workflow_create = build_isolated_workflow_payload(
                None,
                {
                    "name": workflow_name,
                    "note": "Temporary serializer create validation",
                },
            )
            workflow_response = await client.save_workflow(workflow_create)
            workflow_id = extract_object_id(workflow_response)
            workflow_before = await client.get_workflow(workflow_id)
            if workflow_before.get("name") != workflow_name:
                raise RuntimeError("Workflow create read-back did not match")
            result["workflow"].update({"id": workflow_id, "created": True})

            workflow_update = build_isolated_workflow_payload(
                workflow_before,
                {"note": "Temporary serializer update validation"},
            )
            await client.save_workflow(workflow_update)
            workflow_after = await client.get_workflow(workflow_id)
            workflow_diff = requested_diff(
                workflow_before,
                workflow_after,
                {"note": "Temporary serializer update validation"},
            )
            if not all(item["matches_requested"] for item in workflow_diff):
                raise RuntimeError("Workflow update read-back did not match")
            result["workflow"]["updated"] = True

            rule_create = build_isolated_ticketrule_payload(
                None,
                {
                    "name": rule_name,
                    "precedence": 1999,
                    "criteria": [
                        {
                            "id": 0,
                            "rule_id": 0,
                            "fieldname": "requesttypenew",
                            "tablename": "faults",
                            "value_type": "int",
                            "value_type_id": -1,
                            "value_int": 999999,
                            "value_string": "",
                            "value_float": 0.0,
                            "type": 0,
                            "use": 0,
                            "partialmatch": False,
                            "matchseparatedvalues": False,
                            "qualification_criteria_id": 0,
                            "flowsubdetails_criteria_id": 0,
                            "flow_id": 0,
                            "flow_seq": 0,
                            "eventrule_id": 0,
                            "chat_input_suggestion_id": 0,
                            "match_after_start": False,
                            "match_after_target": False,
                        }
                    ],
                    "outcomes": [],
                },
            )
            rule_response = await client.save_ticket_rule(rule_create)
            rule_id = extract_object_id(rule_response)
            rule_before = await client.get_ticket_rule(rule_id)
            if (
                rule_before.get("name") != rule_name
                or rule_before.get("active") is not False
            ):
                raise RuntimeError("Ticket Rule create read-back did not match")
            result["ticket_rule"].update({"id": rule_id, "created": True})

            rule_update = build_isolated_ticketrule_payload(
                rule_before,
                {"precedence": 1998},
            )
            await client.save_ticket_rule(rule_update)
            rule_after = await client.get_ticket_rule(rule_id)
            rule_diff = requested_diff(
                rule_before,
                rule_after,
                {"precedence": 1998},
            )
            if not all(item["matches_requested"] for item in rule_diff):
                raise RuntimeError("Ticket Rule update read-back did not match")
            if (
                not isinstance(rule_after.get("criteria"), list)
                or len(rule_after["criteria"]) != 1
            ):
                raise RuntimeError("Ticket Rule criterion was not preserved")
            result["ticket_rule"]["updated"] = True
        finally:
            cleanup_errors: list[str] = []
            if rule_id is not None:
                try:
                    result["ticket_rule"]["deleted"] = await _verified_delete(
                        client.delete_ticket_rule,
                        client.get_ticket_rule,
                        rule_id,
                    )
                except Exception as exc:
                    error_type = type(exc).__name__
                    cleanup_errors.append(f"Ticket Rule {rule_id}: {error_type}")
            if workflow_id is not None:
                try:
                    result["workflow"]["deleted"] = await _verified_delete(
                        client.delete_workflow,
                        client.get_workflow,
                        workflow_id,
                    )
                except Exception as exc:
                    error_type = type(exc).__name__
                    cleanup_errors.append(f"Workflow {workflow_id}: {error_type}")
            if cleanup_errors:
                joined = "; ".join(cleanup_errors)
                raise RuntimeError(f"Temporary object cleanup failed: {joined}")

    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmation", required=True)
    args = parser.parse_args()
    result = asyncio.run(run(args.confirmation))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
