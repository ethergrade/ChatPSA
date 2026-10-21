# ChatPSA open

ChatPSA open is an open-source MCP server and local conversational web app for
safe HaloPSA administration and troubleshooting. The current MCP surface
exposes fourteen investigation/read tools, two non-executable change-planning
tools, and three guarded Status write tools:

- `halo_connection_status`: validates OAuth and API connectivity without
  returning credentials or tokens.
- `get_ticket_safe`: reads a ticket and returns only explicitly allowlisted
  scalar fields.
- `halo_status_list` / `halo_status_get`: inspect statuses.
- `halo_tickettype_list` / `halo_tickettype_get`: inspect ticket types.
- `halo_workflow_list` / `halo_workflow_get`: inspect workflows, including
  allowlisted steps, actions, and stages.
- `halo_outcome_list` / `halo_outcome_get`: inspect configured outcomes.
- `halo_ticketrule_list` / `halo_ticketrule_get`: inspect ticket rules,
  criteria, and outcomes.
- `halo_workflow_diagnose`: detect structural workflow problems such as missing
  start/end steps, duplicate actions, and dangling transitions.
- `halo_ticket_investigate`: correlate a ticket with its status, type, workflow,
  and diagnostic findings.
- `halo_workflow_change_plan` / `halo_ticketrule_change_plan`: validate and
  preview proposed scalar changes without executing a write; both report the
  remaining recursive-serializer blocker explicitly.
- `halo_status_create` / `halo_status_update` / `halo_status_delete`: controlled
  Status changes with dry-run, explicit opt-in, confirmation, read-back, and
  persisted-value diff.

The intended administrative surface includes controlled configuration,
workflow, and rule changes. Writes are added resource by resource only after
their HaloPSA payloads are validated. Every write remains opt-in and follows
`validate -> snapshot -> write -> read-back -> diff`.

## Safety defaults

- OAuth2 `client_credentials`; tokens and secrets are never returned.
- Write operations are disabled by default. Registered write tools default to
  `dry_run=true` and require both `CHATPSA_ENABLE_WRITES=true` and an exact
  operation-specific confirmation before execution.
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

## Run ChatPSA Web

Start the local conversational interface:

```bash
uv run chatpsa-web
```

Then open [http://127.0.0.1:8765](http://127.0.0.1:8765). The first open
preview supports guided questions such as:

```text
Analizza ticket 12345
Diagnostica workflow 11
Controlla regola 214
Verifica connessione
```

The web app reads credentials only on the Python server, returns the same safe
allowlisted projections used by the MCP tools, stores no browser history, and
binds to `127.0.0.1` only. It is intentionally read-only: write proposals and
approval flows will be added after the resource serializers are validated.

Use `CHATPSA_WEB_PORT` to select another local port.

## Tests

```bash
uv run python -m unittest discover -s tests -v
uv run python -m chatpsa.mcp_smoke --ticket-id YOUR_TEST_TICKET_ID
```

The repository also contains a deliberately restricted live serializer
validation harness for maintainers. It can create only inactive Workflow and
Ticket Rule objects whose names start with `ChatPSA TEMP VALIDATION`, requires
write opt-in plus an exact confirmation, and deletes the objects in a `finally`
cleanup with 404 verification. It is not a general-purpose production write
interface.
