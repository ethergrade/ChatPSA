"""Strict validation, authorization, and diff helpers for controlled writes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from .config import Settings

STATUS_WRITE_FIELDS = frozenset(
    {
        "name",
        "shortname",
        "type",
        "colour",
        "sequence",
        "showonquickchange",
        "includeinloadbalance",
        "dontsendslareminders",
        "slaaction",
        "slaignorerelease",
        "statuschangeto",
        "statuschangetofreq",
        "statusemailid",
        "statusemailfreqdays",
        "statusnochangehours",
        "useworkinghours",
    }
)

WORKFLOW_WRITE_FIELDS = frozenset({"name", "note", "active", "notinuse"})
WORKFLOW_STEP_WRITE_FIELDS = frozenset(
    {
        "fdid",
        "step_id",
        "flow_id",
        "name",
        "isstart",
        "isend",
        "islaststep",
        "stage_number",
        "actions",
    }
)
WORKFLOW_STAGE_WRITE_FIELDS = frozenset(
    {"id", "flow_id", "name", "sequence", "type", "edit_outcome"}
)

TICKETRULE_WRITE_FIELDS = frozenset(
    {
        "name",
        "active",
        "precedence",
        "stopmatching",
        "use",
        "dontshownotification",
        "new_status_id",
        "new_agent_id",
        "new_teamid",
        "new_priority_id",
        "new_sla_id",
        "new_workflow_id",
        "new_template_id",
        "new_category_1_id",
        "new_category_2_id",
        "new_category_3_id",
        "new_category_4_id",
        "new_product_id",
        "criteria",
        "outcomes",
    }
)
TICKETRULE_SCALAR_WRITE_FIELDS = TICKETRULE_WRITE_FIELDS - {
    "criteria",
    "outcomes",
}
TICKETRULE_CRITERION_WRITE_FIELDS = frozenset(
    {
        "id",
        "rule_id",
        "fieldname",
        "tablename",
        "type",
        "use",
        "value_int",
        "value_string",
        "value_float",
        "value_type",
        "value_type_id",
        "partialmatch",
        "matchseparatedvalues",
        "match_after_start",
        "match_after_target",
        "qualification_criteria_id",
        "flowsubdetails_criteria_id",
        "flow_id",
        "flow_seq",
        "eventrule_id",
        "chat_input_suggestion_id",
    }
)
TICKETRULE_OUTCOME_WRITE_FIELDS = frozenset(
    {
        "id",
        "rule_id",
        "fieldid",
        "fieldname",
        "value_type",
        "value_int",
        "value_string",
        "value_float",
        "value_type_id",
        "is_dummy",
    }
)

TEMPORARY_OBJECT_PREFIX = "ChatPSA TEMP VALIDATION "


def validate_scalar_changes(
    changes: Mapping[str, Any],
    *,
    allowed_fields: frozenset[str],
    required_fields: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    if not changes:
        raise ToolError("At least one change is required")
    unknown = sorted(set(changes) - allowed_fields)
    if unknown:
        raise ToolError(f"Unknown or non-writable fields: {', '.join(unknown)}")
    missing = sorted(field for field in required_fields if field not in changes)
    if missing:
        raise ToolError(f"Missing required fields: {', '.join(missing)}")

    validated: dict[str, Any] = {}
    for key, value in changes.items():
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise ToolError(f"{key} must be a scalar value")
        validated[key] = value
    if "name" in validated and not str(validated["name"] or "").strip():
        raise ToolError("name must not be empty")
    return validated


def build_status_payload(
    current: Mapping[str, Any] | None,
    changes: Mapping[str, Any],
) -> dict[str, Any]:
    create = current is None
    validated = validate_scalar_changes(
        changes,
        allowed_fields=STATUS_WRITE_FIELDS,
        required_fields=frozenset({"name"}) if create else frozenset(),
    )
    payload: dict[str, Any] = {"id": 0 if create else current["id"]}
    if current is not None:
        for key in STATUS_WRITE_FIELDS:
            value = current.get(key)
            if value is None or isinstance(value, (str, int, float, bool)):
                payload[key] = value
    payload.update(validated)
    return payload


def _copy_allowlisted_scalars(
    source: Mapping[str, Any], allowed_fields: frozenset[str]
) -> dict[str, Any]:
    return {
        key: value
        for key, value in source.items()
        if key in allowed_fields
        and (value is None or isinstance(value, (str, int, float, bool)))
    }


def _require_temporary_name(name: Any) -> str:
    normalized = str(name or "").strip()
    if not normalized.startswith(TEMPORARY_OBJECT_PREFIX):
        raise ToolError(
            f"Live validation objects must start with {TEMPORARY_OBJECT_PREFIX!r}"
        )
    return normalized


def build_isolated_workflow_payload(
    current: Mapping[str, Any] | None,
    changes: Mapping[str, Any],
) -> dict[str, Any]:
    """Build only the deliberately limited temporary Workflow test shape."""

    validated = validate_scalar_changes(
        changes,
        allowed_fields=WORKFLOW_WRITE_FIELDS,
        required_fields=frozenset({"name"}) if current is None else frozenset(),
    )
    name = validated.get("name", current.get("name") if current else None)
    _require_temporary_name(name)

    if current is None:
        payload: dict[str, Any] = {
            "id": 0,
            "name": name,
            "note": validated.get("note", "Temporary ChatPSA serializer validation"),
            "active": False,
            "notinuse": True,
            "steps": [
                {
                    "fdid": 0,
                    "step_id": 1,
                    "flow_id": 0,
                    "name": "Start",
                    "isstart": True,
                    "isend": False,
                    "islaststep": False,
                    "stage_number": 0,
                    "actions": [],
                }
            ],
            "stages": [],
            "always_allow_actions": [],
            "targets": [],
        }
        payload.update(validated)
        payload["active"] = False
        payload["notinuse"] = True
        return payload

    object_id = current.get("id")
    if not isinstance(object_id, int) or object_id <= 0:
        raise ToolError("Temporary Workflow snapshot has no valid id")
    payload = {"id": object_id}
    payload.update(_copy_allowlisted_scalars(current, WORKFLOW_WRITE_FIELDS))
    payload.update(validated)
    payload["active"] = False
    payload["notinuse"] = True

    steps = current.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ToolError("Temporary Workflow snapshot has no steps")
    payload["steps"] = []
    for step in steps:
        if not isinstance(step, Mapping):
            raise ToolError("Temporary Workflow contains an invalid step")
        safe_step = _copy_allowlisted_scalars(step, WORKFLOW_STEP_WRITE_FIELDS)
        actions = step.get("actions")
        if actions not in (None, []):
            raise ToolError("Temporary Workflow validation does not allow actions")
        safe_step["actions"] = []
        payload["steps"].append(safe_step)

    stages = current.get("stages")
    payload["stages"] = (
        [
            _copy_allowlisted_scalars(stage, WORKFLOW_STAGE_WRITE_FIELDS)
            for stage in stages
            if isinstance(stage, Mapping)
        ]
        if isinstance(stages, list)
        else []
    )
    payload["always_allow_actions"] = []
    payload["targets"] = []
    return payload


def _validate_nested_items(
    items: Any,
    *,
    allowed_fields: frozenset[str],
    label: str,
    strict: bool = True,
) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        raise ToolError(f"{label} must be a list")
    validated: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise ToolError(f"Every {label} item must be an object")
        unknown = sorted(set(item) - allowed_fields)
        if strict and unknown:
            fields = ", ".join(unknown)
            raise ToolError(f"Unknown or non-writable {label} fields: {fields}")
        safe = _copy_allowlisted_scalars(item, allowed_fields)
        if strict and len(safe) != len(item):
            raise ToolError(f"Every {label} field must be scalar")
        validated.append(safe)
    return validated


def build_isolated_ticketrule_payload(
    current: Mapping[str, Any] | None,
    changes: Mapping[str, Any],
) -> dict[str, Any]:
    """Build an inactive, non-operational Ticket Rule validation payload."""

    if not changes:
        raise ToolError("At least one change is required")
    unknown = sorted(set(changes) - TICKETRULE_WRITE_FIELDS)
    if unknown:
        raise ToolError(f"Unknown or non-writable fields: {', '.join(unknown)}")
    if current is None and "name" not in changes:
        raise ToolError("Missing required fields: name")

    name = changes.get("name", current.get("name") if current else None)
    _require_temporary_name(name)
    object_id = 0 if current is None else current.get("id")
    if not isinstance(object_id, int) or object_id < 0:
        raise ToolError("Temporary Ticket Rule snapshot has no valid id")

    payload: dict[str, Any] = {"id": object_id}
    if current is not None:
        payload.update(_copy_allowlisted_scalars(current, TICKETRULE_WRITE_FIELDS))
    for key, value in changes.items():
        if key in {"criteria", "outcomes"}:
            continue
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise ToolError(f"{key} must be a scalar value")
        payload[key] = value

    payload.setdefault("name", name)
    payload["active"] = False
    payload.setdefault("use", 1)
    payload.setdefault("precedence", 1999)
    payload.setdefault("stopmatching", False)
    payload.setdefault("dontshownotification", True)
    for key in (
        "new_status_id",
        "new_agent_id",
        "new_teamid",
        "new_priority_id",
        "new_sla_id",
        "new_workflow_id",
        "new_template_id",
        "new_category_1_id",
        "new_category_2_id",
        "new_category_3_id",
        "new_category_4_id",
        "new_product_id",
    ):
        payload.setdefault(key, -1)

    criteria_source = changes.get(
        "criteria", current.get("criteria", []) if current else []
    )
    outcomes_source = changes.get(
        "outcomes", current.get("outcomes", []) if current else []
    )
    payload["criteria"] = _validate_nested_items(
        criteria_source,
        allowed_fields=TICKETRULE_CRITERION_WRITE_FIELDS,
        label="criteria",
        strict="criteria" in changes,
    )
    payload["outcomes"] = _validate_nested_items(
        outcomes_source,
        allowed_fields=TICKETRULE_OUTCOME_WRITE_FIELDS,
        label="outcomes",
        strict="outcomes" in changes,
    )
    payload["events"] = []
    payload["olas"] = []
    payload["database_lookups"] = []
    payload["access_control"] = []
    return payload


def authorize_write(
    settings: Settings,
    *,
    dry_run: bool,
    confirmation: str,
    expected_confirmation: str,
) -> None:
    if dry_run:
        return
    if not settings.enable_writes:
        raise ToolError(
            "Writes are disabled. Set CHATPSA_ENABLE_WRITES=true to allow execution."
        )
    if confirmation != expected_confirmation:
        raise ToolError(
            f"Confirmation mismatch. Expected exactly: {expected_confirmation}"
        )


def requested_diff(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any],
    requested_fields: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return [
        {
            "field": field,
            "before": before.get(field) if before is not None else None,
            "requested": requested,
            "persisted": after.get(field),
            "matches_requested": after.get(field) == requested,
        }
        for field, requested in requested_fields.items()
    ]


def build_scalar_change_plan(
    current: Mapping[str, Any],
    changes: Mapping[str, Any],
    *,
    allowed_fields: frozenset[str],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Validate scalar changes and return a non-executable projected state."""

    validated = validate_scalar_changes(changes, allowed_fields=allowed_fields)
    projected = dict(current)
    projected.update(validated)
    return validated, projected, requested_diff(current, projected, validated)


def extract_object_id(payload: Any) -> int:
    candidates: list[Any]
    if isinstance(payload, list):
        candidates = payload
    else:
        candidates = [payload]
    for candidate in candidates:
        if isinstance(candidate, Mapping):
            object_id = candidate.get("id")
            if isinstance(object_id, int) and object_id > 0:
                return object_id
    raise RuntimeError("HaloPSA write response did not contain a created object ID")
