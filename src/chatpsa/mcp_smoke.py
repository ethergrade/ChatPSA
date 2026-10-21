"""End-to-end stdio MCP smoke test with secret-safe output."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Mapping
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from .config import project_root
from .safe import SAFE_TICKET_FIELDS


def _mapping_from_result(result: Any) -> Mapping[str, Any]:
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, Mapping):
        nested = structured.get("result")
        if isinstance(nested, Mapping):
            return nested
        return structured

    for item in getattr(result, "content", []):
        text = getattr(item, "text", None)
        if not isinstance(text, str):
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, Mapping):
            return parsed
    raise RuntimeError("MCP tool did not return an object")


async def run(ticket_id: int) -> None:
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "chatpsa.server"],
        cwd=project_root(),
    )
    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            expected = {"halo_connection_status", "get_ticket_safe"}
            if names != expected:
                raise RuntimeError(f"Unexpected MCP tools: {sorted(names)}")

            connection_result = await session.call_tool("halo_connection_status", {})
            if connection_result.is_error:
                raise RuntimeError("halo_connection_status returned an MCP error")
            connection = _mapping_from_result(connection_result)
            if connection.get("connected") is not True:
                raise RuntimeError("halo_connection_status did not confirm connectivity")
            if connection.get("writes_enabled") is not False:
                raise RuntimeError("Writes must remain disabled during the smoke test")

            ticket_result = await session.call_tool(
                "get_ticket_safe", {"ticket_id": ticket_id}
            )
            if ticket_result.is_error:
                raise RuntimeError("get_ticket_safe returned an MCP error")
            ticket = _mapping_from_result(ticket_result)
            allowed = set(SAFE_TICKET_FIELDS) | {"assets_count"}
            unexpected = set(ticket) - allowed
            if unexpected:
                raise RuntimeError(
                    f"get_ticket_safe returned non-allowlisted keys: {sorted(unexpected)}"
                )
            if ticket.get("id") != ticket_id:
                raise RuntimeError("get_ticket_safe returned the wrong ticket")

    print(
        "MCP smoke test: OK; 2 read-only tools registered; "
        "connection and safe ticket projection validated."
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticket-id", type=int, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.ticket_id))


if __name__ == "__main__":
    main()
