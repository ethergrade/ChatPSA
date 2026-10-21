# ChatPSA open

ChatPSA open is an open-source MCP server and internal agent desk for safe
HaloPSA and Domotz troubleshooting. Its retrieval layer combines curated
guides, optional tenant-private notes, safe live data, and image analysis with
OpenAI. The current MCP surface includes
investigation/read tools, non-executable change-planning
tools, and three guarded Status write tools:

- `halo_connection_status`: validates OAuth and API connectivity without
  returning credentials or tokens.
- `get_ticket_safe`: reads a ticket and returns only explicitly allowlisted
  scalar fields.
- `halo_status_list` / `halo_status_get`: inspect statuses.
- `halo_status_create` / `halo_status_update` / `halo_status_delete`: controlled
  Status changes with dry-run, explicit opt-in, confirmation, read-back, and
  persisted-value diff.
- `halo_tickettype_list` / `halo_tickettype_get`: inspect ticket types.
- `halo_tickettype_create` / `halo_tickettype_update` /
  `halo_tickettype_delete`: create a hidden draft Ticket Type, then safely
  configure or remove it with snapshot and read-back verification.
- `halo_category_list` / `halo_category_get`: inspect ticket categories.
- `halo_category_create` / `halo_category_update` / `halo_category_delete`:
  controlled ticket-category changes with the same dry-run and verification
  safeguards.
- `halo_workflow_list` / `halo_workflow_get`: inspect workflows, including
  allowlisted steps, actions, and stages.
- `halo_outcome_list` / `halo_outcome_get`: inspect configured outcomes.
- `halo_ticketrule_list` / `halo_ticketrule_get`: inspect ticket rules,
  criteria, and outcomes.
- `halo_workflow_diagnose`: detect structural workflow problems such as missing
  start/end steps, duplicate actions, and dangling transitions.
- `halo_ticket_investigate`: correlate a ticket with its status, type, workflow,
  and diagnostic findings.
- `halo_kb_search` / `halo_kb_get`: search and read the live HaloPSA Knowledge
  Base using bounded deny-by-default projections.
- `halo_kb_tags`: read the tag catalogue directly from HaloPSA.
- `halo_kb_article_create_plan`: prepare an inactive article draft using only
  tag IDs that exist in Halo; execution remains approval-gated and disabled
  until its tenant serializer is validated.
- `halo_workflow_change_plan` / `halo_ticketrule_change_plan`: validate and
  preview proposed scalar changes without executing a write; both report the
  remaining recursive-serializer blocker explicitly.

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

The web app can answer general process questions, correlate HaloPSA and Domotz,
and analyze up to four PNG/JPEG/WebP/GIF images. It uses the configured OpenAI
model with `store=false`; `OPENAI_IMAGE_DETAIL=low` is the cost-conscious
default. Credentials remain server-side and live results use deny-by-default
projections.

Public guides live in `knowledge/guides`. Tenant-specific memory is loaded
only from explicitly allowlisted local Markdown files and `knowledge/tenant`;
that directory is excluded from Git. Retrieval is query-scoped, bounded, and
credential-shaped lines are removed before context is sent to the model.

Requests to create or modify a Rule or Workflow are never executed from chat.
They are stored in a local approval queue and can notify the configured
approvers by email. In production, use verified OIDC identity headers from a
trusted reverse proxy so the requester cannot impersonate another agent. See
`deploy/debian/README.md` and `.env.example`.

The same governance applies to Knowledge Base creation. ChatPSA can search the
live HaloPSA KB, use approved article content as evidence, retrieve the current
Halo tag catalogue, and prepare an inactive draft. Publication is never an
implicit side effect of a chat answer.

Administrators have an approval centre showing pending, executing, completed,
and failed requests. Only structured actions named in
`CHATPSA_APPROVAL_EXECUTION_ACTIONS` can be approved for execution. KB drafts
and Release Notes are written through dedicated serializers and immediately
read back from HaloPSA; the verified result or failure remains in the immutable
approval history.

In temporary token mode, administrators and ServiceDesk agents use separate
tokens. The shared agent token receives one non-personal shared history and
cannot claim an email address. Optional personal tokens can be bound server-side
through `CHATPSA_AGENT_IDENTITIES_JSON`; verified OIDC remains the preferred
production identity. Agent tokens can never be treated as approver tokens.

Conversations and investigations are persisted in an append-only SQLite store,
scoped to the authenticated identity. A conversation can be opened and renamed;
there is deliberately no delete route or storage delete operation.

Use `CHATPSA_WEB_PORT` to select another local port. Docker Compose deployment
for an internal Debian host is included; by default it remains bound to
`127.0.0.1` for use behind an HTTPS/OIDC reverse proxy.

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
