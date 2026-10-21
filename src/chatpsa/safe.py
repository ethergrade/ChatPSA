"""Deny-by-default projections for data returned to MCP clients."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


SAFE_TICKET_FIELDS = (
    "id",
    "summary",
    "status_id",
    "status_name",
    "tickettype_id",
    "tickettype_name",
    "client_id",
    "client_name",
    "site_id",
    "site_name",
    "user_id",
    "user_name",
    "team_id",
    "team",
    "agent_id",
    "workflow_id",
    "workflow_name",
    "workflow_step",
    "workflow_seq",
    "priority_id",
    "sla_id",
    "sla_name",
    "dateoccurred",
    "last_update_date",
)

SAFE_AGENT_FIELDS = ("id", "name")


def project_fields(source: Mapping[str, Any], allowlist: tuple[str, ...]) -> dict[str, Any]:
    """Return only explicitly permitted scalar values from a source object."""

    projected: dict[str, Any] = {}
    for key in allowlist:
        if key not in source:
            continue
        value = source[key]
        if value is None or isinstance(value, (str, int, float, bool)):
            projected[key] = value
    return projected


def safe_ticket_projection(ticket: Mapping[str, Any]) -> dict[str, Any]:
    projected = project_fields(ticket, SAFE_TICKET_FIELDS)
    assets = ticket.get("assets")
    if isinstance(assets, list):
        projected["assets_count"] = len(assets)
    return projected


def safe_agent_projection(agent: Mapping[str, Any]) -> dict[str, Any]:
    return project_fields(agent, SAFE_AGENT_FIELDS)
