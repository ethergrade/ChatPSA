"""ChatPSA MCP server for safe investigation and controlled administration."""

from __future__ import annotations

from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer

from .change_control import (
    CATEGORY_WRITE_FIELDS,
    STATUS_WRITE_FIELDS,
    TICKETTYPE_WRITE_FIELDS,
    TICKETRULE_SCALAR_WRITE_FIELDS,
    WORKFLOW_WRITE_FIELDS,
    authorize_write,
    build_category_payload,
    build_scalar_change_plan,
    build_status_payload,
    build_tickettype_payload,
    extract_object_id,
    requested_diff,
    validate_scalar_changes,
)
from .client import HaloClient
from .config import Settings
from .diagnostics import diagnose_workflow, investigate_ticket
from .kb import build_kb_article_create_plan
from .safe import (
    safe_agent_projection,
    safe_category_projection,
    safe_kb_article_projection,
    safe_kb_tag_projection,
    safe_outcome_projection,
    safe_status_projection,
    safe_ticket_projection,
    safe_ticketrule_projection,
    safe_tickettype_projection,
    safe_workflow_projection,
)

mcp = MCPServer(
    "ChatPSA",
    instructions=(
        "Safe HaloPSA investigation and administration. Results use explicit "
        "allowlists. Writes default to dry-run and require configuration opt-in, "
        "exact confirmation, read-back, and diff."
    ),
    log_level="WARNING",
)


@mcp.tool()
async def halo_connection_status() -> dict[str, Any]:
    """Check OAuth/API connectivity without returning tokens or credentials."""

    settings = Settings.from_env()
    async with HaloClient(settings) as client:
        agent = await client.get_agent_me()
    return {
        "connected": True,
        "writes_enabled": settings.enable_writes,
        "identity": safe_agent_projection(agent),
    }


@mcp.tool()
async def get_ticket_safe(ticket_id: int) -> dict[str, Any]:
    """Read one ticket and return only explicitly allowlisted, non-nested fields."""

    settings = Settings.from_env()
    async with HaloClient(settings) as client:
        ticket = await client.get_ticket(ticket_id)
    return safe_ticket_projection(ticket)


@mcp.tool()
async def halo_status_list() -> dict[str, Any]:
    """List HaloPSA statuses using a reviewed scalar allowlist."""

    settings = Settings.from_env()
    async with HaloClient(settings) as client:
        statuses = await client.list_statuses()
    items = [safe_status_projection(status) for status in statuses]
    return {"count": len(items), "items": items}


@mcp.tool()
async def halo_status_get(status_id: int) -> dict[str, Any]:
    """Get one HaloPSA status using a reviewed scalar allowlist."""

    settings = Settings.from_env()
    async with HaloClient(settings) as client:
        status = await client.get_status(status_id)
    return safe_status_projection(status)


@mcp.tool()
async def halo_tickettype_list() -> dict[str, Any]:
    """List HaloPSA ticket types using a reviewed scalar allowlist."""

    settings = Settings.from_env()
    async with HaloClient(settings) as client:
        tickettypes = await client.list_ticket_types()
    items = [safe_tickettype_projection(item) for item in tickettypes]
    return {"count": len(items), "items": items}


@mcp.tool()
async def halo_tickettype_get(tickettype_id: int) -> dict[str, Any]:
    """Get one HaloPSA ticket type using a reviewed scalar allowlist."""

    settings = Settings.from_env()
    async with HaloClient(settings) as client:
        tickettype = await client.get_ticket_type(tickettype_id)
    return safe_tickettype_projection(tickettype)


@mcp.tool()
async def halo_category_list() -> dict[str, Any]:
    """List HaloPSA ticket categories using a reviewed scalar allowlist."""

    settings = Settings.from_env()
    async with HaloClient(settings) as client:
        categories = await client.list_categories()
    items = [safe_category_projection(item) for item in categories]
    return {"count": len(items), "items": items}


@mcp.tool()
async def halo_category_get(category_id: int) -> dict[str, Any]:
    """Get one HaloPSA ticket category using a reviewed scalar allowlist."""

    settings = Settings.from_env()
    async with HaloClient(settings) as client:
        category = await client.get_category(category_id)
    return safe_category_projection(category)


@mcp.tool()
async def halo_workflow_list() -> dict[str, Any]:
    """List HaloPSA workflows using a reviewed scalar allowlist."""

    settings = Settings.from_env()
    async with HaloClient(settings) as client:
        workflows = await client.list_workflows()
    items = [safe_workflow_projection(workflow) for workflow in workflows]
    return {"count": len(items), "items": items}


@mcp.tool()
async def halo_workflow_get(workflow_id: int) -> dict[str, Any]:
    """Get a workflow with allowlisted steps, actions, and stages."""

    settings = Settings.from_env()
    async with HaloClient(settings) as client:
        workflow = await client.get_workflow(workflow_id)
    return safe_workflow_projection(workflow)


@mcp.tool()
async def halo_outcome_list() -> dict[str, Any]:
    """List configured HaloPSA outcomes using a reviewed scalar allowlist."""

    settings = Settings.from_env()
    async with HaloClient(settings) as client:
        outcomes = await client.list_outcomes()
    items = [safe_outcome_projection(outcome) for outcome in outcomes]
    return {"count": len(items), "items": items}


@mcp.tool()
async def halo_outcome_get(outcome_id: int) -> dict[str, Any]:
    """Get one configured HaloPSA outcome using a reviewed scalar allowlist."""

    settings = Settings.from_env()
    async with HaloClient(settings) as client:
        outcome = await client.get_outcome(outcome_id)
    return safe_outcome_projection(outcome)


@mcp.tool()
async def halo_ticketrule_list() -> dict[str, Any]:
    """List ticket rules with allowlisted criteria and outcomes."""

    settings = Settings.from_env()
    async with HaloClient(settings) as client:
        rules = await client.list_ticket_rules()
    items = [safe_ticketrule_projection(rule) for rule in rules]
    return {"count": len(items), "items": items}


@mcp.tool()
async def halo_ticketrule_get(ticketrule_id: int) -> dict[str, Any]:
    """Get one ticket rule with allowlisted criteria and outcomes."""

    settings = Settings.from_env()
    async with HaloClient(settings) as client:
        rule = await client.get_ticket_rule(ticketrule_id)
    return safe_ticketrule_projection(rule)


@mcp.tool()
async def halo_kb_search(query: str, limit: int = 8) -> dict[str, Any]:
    """Search active HaloPSA KB articles and return safe, bounded projections."""

    settings = Settings.from_env()
    async with HaloClient(settings) as client:
        articles = await client.search_kb_articles(query, limit=limit)
    items = [safe_kb_article_projection(article) for article in articles]
    return {"query": query, "count": len(items), "items": items}


@mcp.tool()
async def halo_kb_get(article_id: int) -> dict[str, Any]:
    """Read one HaloPSA KB article with reviewed fields and cleaned text."""

    settings = Settings.from_env()
    async with HaloClient(settings) as client:
        article = await client.get_kb_article(article_id)
    return safe_kb_article_projection(article)


@mcp.tool()
async def halo_kb_tags() -> dict[str, Any]:
    """List tag IDs and names directly from the connected HaloPSA tenant."""

    settings = Settings.from_env()
    async with HaloClient(settings) as client:
        tags = await client.list_kb_tags()
    items = [safe_kb_tag_projection(tag) for tag in tags]
    return {"count": len(items), "items": items}


@mcp.tool()
async def halo_kb_article_create_plan(
    title: str,
    description: str,
    resolution: str,
    tag_ids: list[int],
) -> dict[str, Any]:
    """Prepare an inactive KB draft using only tag IDs read from HaloPSA."""

    settings = Settings.from_env()
    async with HaloClient(settings) as client:
        tags = await client.list_kb_tags()
    payload = build_kb_article_create_plan(
        title=title,
        description=description,
        resolution=resolution,
        tag_ids=tag_ids,
        available_tags=tags,
    )
    return {
        "operation": "create_kb_article_draft",
        "dry_run": True,
        "execution_available": False,
        "payload": payload,
        "approval_required": True,
        "blocker": (
            "The tenant-specific KB serializer must be validated with an "
            "isolated inactive article before execution is enabled."
        ),
    }


@mcp.tool()
async def halo_workflow_diagnose(workflow_id: int) -> dict[str, Any]:
    """Analyze workflow topology and report structural troubleshooting findings."""

    settings = Settings.from_env()
    async with HaloClient(settings) as client:
        workflow = await client.get_workflow(workflow_id)
    return diagnose_workflow(workflow)


@mcp.tool()
async def halo_ticket_investigate(ticket_id: int) -> dict[str, Any]:
    """Correlate a ticket with status, type, workflow, and structural findings."""

    settings = Settings.from_env()
    async with HaloClient(settings) as client:
        ticket = await client.get_ticket(ticket_id)
        status_id = ticket.get("status_id")
        tickettype_id = ticket.get("tickettype_id")
        workflow_id = ticket.get("workflow_id")
        status = (
            await client.get_status(status_id)
            if isinstance(status_id, int) and status_id > 0
            else None
        )
        tickettype = (
            await client.get_ticket_type(tickettype_id)
            if isinstance(tickettype_id, int) and tickettype_id > 0
            else None
        )
        workflow = (
            await client.get_workflow(workflow_id)
            if isinstance(workflow_id, int) and workflow_id > 0
            else None
        )
    return investigate_ticket(
        ticket,
        status=status,
        tickettype=tickettype,
        workflow=workflow,
    )


@mcp.tool()
async def halo_workflow_change_plan(
    workflow_id: int,
    changes: dict[str, Any],
) -> dict[str, Any]:
    """Plan safe Workflow metadata changes without executing a write."""

    settings = Settings.from_env()
    async with HaloClient(settings) as client:
        before = await client.get_workflow(workflow_id)
    validated, projected, diff = build_scalar_change_plan(
        before,
        changes,
        allowed_fields=WORKFLOW_WRITE_FIELDS,
    )
    return {
        "operation": "plan_workflow_metadata_update",
        "dry_run": True,
        "execution_available": False,
        "workflow_id": workflow_id,
        "before": safe_workflow_projection(before),
        "requested_changes": validated,
        "projected_after": safe_workflow_projection(projected),
        "diff": diff,
        "blocker": (
            "Production execution remains disabled until recursive Workflow "
            "actions, notifications, targets, access control, and layout "
            "preservation are validated."
        ),
    }


@mcp.tool()
async def halo_ticketrule_change_plan(
    ticketrule_id: int,
    changes: dict[str, Any],
) -> dict[str, Any]:
    """Plan safe Ticket Rule scalar changes without executing a write."""

    settings = Settings.from_env()
    async with HaloClient(settings) as client:
        before = await client.get_ticket_rule(ticketrule_id)
    validated, projected, diff = build_scalar_change_plan(
        before,
        changes,
        allowed_fields=TICKETRULE_SCALAR_WRITE_FIELDS,
    )
    return {
        "operation": "plan_ticketrule_scalar_update",
        "dry_run": True,
        "execution_available": False,
        "ticketrule_id": ticketrule_id,
        "before": safe_ticketrule_projection(before),
        "requested_changes": validated,
        "projected_after": safe_ticketrule_projection(projected),
        "diff": diff,
        "blocker": (
            "Production execution remains disabled until recursive Ticket Rule "
            "criteria, outcomes, events, targets, and access-control "
            "preservation are validated."
        ),
    }


@mcp.tool()
async def halo_status_create(
    values: dict[str, Any],
    dry_run: bool = True,
    confirmation: str = "",
) -> dict[str, Any]:
    """Plan or create a Status with strict fields, confirmation, and read-back."""

    settings = Settings.from_env()
    payload = build_status_payload(None, values)
    expected = "CREATE STATUS"
    authorize_write(
        settings,
        dry_run=dry_run,
        confirmation=confirmation,
        expected_confirmation=expected,
    )
    if dry_run:
        return {
            "operation": "create_status",
            "dry_run": True,
            "writes_enabled": settings.enable_writes,
            "confirmation_required": expected,
            "payload": payload,
        }

    async with HaloClient(settings) as client:
        response = await client.save_status(payload)
        status_id = extract_object_id(response)
        persisted = await client.get_status(status_id)
    return {
        "operation": "create_status",
        "dry_run": False,
        "status": safe_status_projection(persisted),
        "diff": requested_diff(None, persisted, values),
    }


@mcp.tool()
async def halo_status_update(
    status_id: int,
    changes: dict[str, Any],
    dry_run: bool = True,
    confirmation: str = "",
) -> dict[str, Any]:
    """Plan or update a Status with snapshot, read-back, and requested-field diff."""

    settings = Settings.from_env()
    validated_changes = validate_scalar_changes(
        changes,
        allowed_fields=STATUS_WRITE_FIELDS,
    )
    expected = f"UPDATE STATUS {status_id}"
    async with HaloClient(settings) as client:
        before = await client.get_status(status_id)
        payload = build_status_payload(before, validated_changes)
        authorize_write(
            settings,
            dry_run=dry_run,
            confirmation=confirmation,
            expected_confirmation=expected,
        )
        if dry_run:
            return {
                "operation": "update_status",
                "dry_run": True,
                "writes_enabled": settings.enable_writes,
                "confirmation_required": expected,
                "before": safe_status_projection(before),
                "requested_changes": validated_changes,
            }
        await client.save_status(payload)
        persisted = await client.get_status(status_id)
    return {
        "operation": "update_status",
        "dry_run": False,
        "before": safe_status_projection(before),
        "after": safe_status_projection(persisted),
        "diff": requested_diff(before, persisted, validated_changes),
    }


@mcp.tool()
async def halo_status_delete(
    status_id: int,
    dry_run: bool = True,
    confirmation: str = "",
) -> dict[str, Any]:
    """Plan or delete a Status with snapshot, confirmation, and 404 verification."""

    settings = Settings.from_env()
    expected = f"DELETE STATUS {status_id}"
    async with HaloClient(settings) as client:
        before = await client.get_status(status_id)
        authorize_write(
            settings,
            dry_run=dry_run,
            confirmation=confirmation,
            expected_confirmation=expected,
        )
        if dry_run:
            return {
                "operation": "delete_status",
                "dry_run": True,
                "writes_enabled": settings.enable_writes,
                "confirmation_required": expected,
                "before": safe_status_projection(before),
            }
        await client.delete_status(status_id)
        deleted = False
        try:
            await client.get_status(status_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            deleted = True
    if not deleted:
        raise RuntimeError("Status delete read-back failed: object still exists")
    return {
        "operation": "delete_status",
        "dry_run": False,
        "before": safe_status_projection(before),
        "verified_deleted": True,
    }


@mcp.tool()
async def halo_tickettype_create(
    values: dict[str, Any], dry_run: bool = True, confirmation: str = ""
) -> dict[str, Any]:
    """Plan or create an initially hidden Ticket Type with read-back verification."""

    settings = Settings.from_env()
    payload = build_tickettype_payload(None, values)
    expected = "CREATE TICKETTYPE"
    authorize_write(settings, dry_run=dry_run, confirmation=confirmation, expected_confirmation=expected)
    if dry_run:
        return {"operation": "create_tickettype", "dry_run": True, "writes_enabled": settings.enable_writes, "confirmation_required": expected, "payload": payload}
    async with HaloClient(settings) as client:
        response = await client.save_ticket_type(payload)
        object_id = extract_object_id(response)
        persisted = await client.get_ticket_type(object_id)
    return {"operation": "create_tickettype", "dry_run": False, "tickettype": safe_tickettype_projection(persisted), "diff": requested_diff(None, persisted, values)}


@mcp.tool()
async def halo_tickettype_update(
    tickettype_id: int, changes: dict[str, Any], dry_run: bool = True, confirmation: str = ""
) -> dict[str, Any]:
    """Plan or update a Ticket Type with a snapshot, read-back, and diff."""

    settings = Settings.from_env()
    validated = validate_scalar_changes(changes, allowed_fields=TICKETTYPE_WRITE_FIELDS)
    expected = f"UPDATE TICKETTYPE {tickettype_id}"
    async with HaloClient(settings) as client:
        before = await client.get_ticket_type(tickettype_id)
        payload = build_tickettype_payload(before, validated)
        authorize_write(settings, dry_run=dry_run, confirmation=confirmation, expected_confirmation=expected)
        if dry_run:
            return {"operation": "update_tickettype", "dry_run": True, "writes_enabled": settings.enable_writes, "confirmation_required": expected, "before": safe_tickettype_projection(before), "requested_changes": validated}
        await client.save_ticket_type(payload)
        persisted = await client.get_ticket_type(tickettype_id)
    return {"operation": "update_tickettype", "dry_run": False, "before": safe_tickettype_projection(before), "after": safe_tickettype_projection(persisted), "diff": requested_diff(before, persisted, validated)}


@mcp.tool()
async def halo_tickettype_delete(
    tickettype_id: int, dry_run: bool = True, confirmation: str = ""
) -> dict[str, Any]:
    """Plan or delete a Ticket Type with a required confirmation and 404 read-back."""

    settings = Settings.from_env()
    expected = f"DELETE TICKETTYPE {tickettype_id}"
    async with HaloClient(settings) as client:
        before = await client.get_ticket_type(tickettype_id)
        authorize_write(settings, dry_run=dry_run, confirmation=confirmation, expected_confirmation=expected)
        if dry_run:
            return {"operation": "delete_tickettype", "dry_run": True, "writes_enabled": settings.enable_writes, "confirmation_required": expected, "before": safe_tickettype_projection(before)}
        await client.delete_ticket_type(tickettype_id)
        try:
            await client.get_ticket_type(tickettype_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return {"operation": "delete_tickettype", "dry_run": False, "before": safe_tickettype_projection(before), "verified_deleted": True}
            raise
    raise RuntimeError("Ticket Type delete read-back failed: object still exists")


@mcp.tool()
async def halo_category_create(
    values: dict[str, Any], dry_run: bool = True, confirmation: str = ""
) -> dict[str, Any]:
    """Plan or create a HaloPSA ticket category with read-back verification."""

    settings = Settings.from_env()
    payload = build_category_payload(None, values)
    expected = "CREATE CATEGORY"
    authorize_write(settings, dry_run=dry_run, confirmation=confirmation, expected_confirmation=expected)
    if dry_run:
        return {"operation": "create_category", "dry_run": True, "writes_enabled": settings.enable_writes, "confirmation_required": expected, "payload": payload}
    async with HaloClient(settings) as client:
        response = await client.save_category(payload)
        object_id = extract_object_id(response)
        persisted = await client.get_category(object_id)
    return {"operation": "create_category", "dry_run": False, "category": safe_category_projection(persisted), "diff": requested_diff(None, persisted, values)}


@mcp.tool()
async def halo_category_update(
    category_id: int, changes: dict[str, Any], dry_run: bool = True, confirmation: str = ""
) -> dict[str, Any]:
    """Plan or update a category with a snapshot, read-back, and diff."""

    settings = Settings.from_env()
    validated = validate_scalar_changes(changes, allowed_fields=CATEGORY_WRITE_FIELDS)
    expected = f"UPDATE CATEGORY {category_id}"
    async with HaloClient(settings) as client:
        before = await client.get_category(category_id)
        payload = build_category_payload(before, validated)
        authorize_write(settings, dry_run=dry_run, confirmation=confirmation, expected_confirmation=expected)
        if dry_run:
            return {"operation": "update_category", "dry_run": True, "writes_enabled": settings.enable_writes, "confirmation_required": expected, "before": safe_category_projection(before), "requested_changes": validated}
        await client.save_category(payload)
        persisted = await client.get_category(category_id)
    return {"operation": "update_category", "dry_run": False, "before": safe_category_projection(before), "after": safe_category_projection(persisted), "diff": requested_diff(before, persisted, validated)}


@mcp.tool()
async def halo_category_delete(
    category_id: int, dry_run: bool = True, confirmation: str = ""
) -> dict[str, Any]:
    """Plan or delete a category with a required confirmation and 404 read-back."""

    settings = Settings.from_env()
    expected = f"DELETE CATEGORY {category_id}"
    async with HaloClient(settings) as client:
        before = await client.get_category(category_id)
        authorize_write(settings, dry_run=dry_run, confirmation=confirmation, expected_confirmation=expected)
        if dry_run:
            return {"operation": "delete_category", "dry_run": True, "writes_enabled": settings.enable_writes, "confirmation_required": expected, "before": safe_category_projection(before)}
        await client.delete_category(category_id)
        try:
            await client.get_category(category_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return {"operation": "delete_category", "dry_run": False, "before": safe_category_projection(before), "verified_deleted": True}
            raise
    raise RuntimeError("Category delete read-back failed: object still exists")


def main() -> None:
    settings = Settings.from_env()
    if settings.transport not in {"stdio", "sse", "streamable-http"}:
        raise RuntimeError(
            "CHATPSA_TRANSPORT must be stdio, sse, or streamable-http"
        )
    mcp.run(transport=settings.transport)


if __name__ == "__main__":
    main()
