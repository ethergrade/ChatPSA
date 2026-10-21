"""Live, secret-safe connectivity smoke test."""

from __future__ import annotations

import asyncio

from .client import HaloClient
from .config import Settings


async def run() -> None:
    settings = Settings.from_env()
    async with HaloClient(settings) as client:
        await client.get_agent_me()
    write_state = "enabled" if settings.enable_writes else "disabled"
    print(f"HaloPSA smoke test: OK; writes are {write_state}.")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
