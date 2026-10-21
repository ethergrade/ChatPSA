"""Application configuration loaded from the project-local environment file."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def project_root() -> Path:
    """Return the repository root without depending on the process cwd."""

    return Path(__file__).resolve().parents[2]


def _parse_bool(name: str, value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be true or false")


@dataclass(frozen=True)
class Settings:
    base_url: str
    client_id: str
    client_secret: str = field(repr=False)
    scope: str = "all"
    enable_writes: bool = False
    transport: str = "stdio"
    timeout_seconds: float = 30.0
    env_file: Path | None = field(default=None, repr=False)

    @classmethod
    def from_env(cls, env_path: str | Path | None = None) -> Settings:
        """Load settings with process variables taking precedence over `.env`.

        The default path is resolved from this module, so launching ChatPSA from a
        different working directory does not change which `.env` is loaded.
        """

        configured_path = env_path or os.environ.get("CHATPSA_ENV_FILE")
        candidates = (
            [Path(configured_path).expanduser()]
            if configured_path
            else [project_root() / ".env"]
        )
        selected = next((path.resolve() for path in candidates if path.is_file()), None)
        if selected is not None:
            load_dotenv(dotenv_path=selected, override=False)

        required_names = ("HALO_BASE_URL", "HALO_CLIENT_ID", "HALO_CLIENT_SECRET")
        missing = [name for name in required_names if not os.environ.get(name, "").strip()]
        if missing:
            location = str(selected) if selected else "no environment file found"
            raise RuntimeError(
                "Missing required environment variables: "
                + ", ".join(missing)
                + f" ({location})"
            )

        base_url = os.environ["HALO_BASE_URL"].strip().rstrip("/")
        if not base_url.startswith(("https://", "http://")):
            raise RuntimeError("HALO_BASE_URL must start with https:// or http://")

        timeout_raw = os.environ.get("HALO_TIMEOUT_SECONDS", "30").strip()
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError as exc:
            raise RuntimeError("HALO_TIMEOUT_SECONDS must be a number") from exc
        if timeout_seconds <= 0:
            raise RuntimeError("HALO_TIMEOUT_SECONDS must be greater than zero")

        return cls(
            base_url=base_url,
            client_id=os.environ["HALO_CLIENT_ID"].strip(),
            client_secret=os.environ["HALO_CLIENT_SECRET"].strip(),
            scope=os.environ.get("HALO_SCOPE", "all").strip() or "all",
            enable_writes=_parse_bool(
                "CHATPSA_ENABLE_WRITES",
                os.environ.get("CHATPSA_ENABLE_WRITES", "false"),
            ),
            transport=os.environ.get("CHATPSA_TRANSPORT", "stdio").strip() or "stdio",
            timeout_seconds=timeout_seconds,
            env_file=selected,
        )
