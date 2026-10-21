"""ChatPSA MCP server exposing a deliberately small read-only surface."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from .client import HaloClient
from .config import Settings
from .safe import safe_agent_projection, safe_ticket_projection


mcp = MCPServer(
    "ChatPSA",
    instructions=(
        "Safe, read-only HaloPSA access. Ticket results are projected through an "
        "explicit allowlist; unrecognized fields are never returned."
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


def main() -> None:
    settings = Settings.from_env()
    if settings.transport not in {"stdio", "sse", "streamable-http"}:
        raise RuntimeError(
            "CHATPSA_TRANSPORT must be stdio, sse, or streamable-http"
        )
    mcp.run(transport=settings.transport)


if __name__ == "__main__":
    main()
