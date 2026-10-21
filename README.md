# ChatPSA

ChatPSA is an early-stage MCP server for safe HaloPSA access. The current
surface is read-only and exposes two tools:

- `halo_connection_status`: validates OAuth and API connectivity without
  returning credentials or tokens.
- `get_ticket_safe`: reads a ticket and returns only explicitly allowlisted
  scalar fields.

## Safety defaults

- OAuth2 `client_credentials`; tokens and secrets are never returned.
- Write operations are disabled by default and no write tool is currently
  registered.
- Ticket projections are deny-by-default: new or nested Halo fields are dropped
  unless deliberately reviewed and allowlisted.
- A 401 response refreshes OAuth and retries the identical request once only.
- `.env`, local investigation files, outputs, and private project logs are
  excluded from Git.

## Setup

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env
# Fill in the local HaloPSA credentials, then:
uv sync
uv run python -m chatpsa.smoke
```

The `.env` path is resolved from the installed source tree/project root, not
from the shell's current working directory. Set `CHATPSA_ENV_FILE` only when an
explicit alternative file is required. Existing process variables take
precedence over values in the file.

## Run the MCP server

```bash
uv run chatpsa
```

The default transport is `stdio`. `sse` and `streamable-http` may be selected
with `CHATPSA_TRANSPORT`.

## Tests

```bash
uv run python -m unittest discover -s tests -v
uv run python -m chatpsa.mcp_smoke --ticket-id YOUR_TEST_TICKET_ID
```
