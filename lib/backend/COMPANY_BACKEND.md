# ARC Company backend

ARC exposes one backend product: **ARC Company**, with a temporary-session CEO-led
organization and role-scoped tools.

## Run locally

```powershell
cd lib/backend
py -m pip install -r requirements.lock
py -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

The API documentation is available at `http://127.0.0.1:8000/docs`.

## Main API

- `GET /health/live` checks that the process is running.
- `GET /health/ready` checks in-memory state, access configuration, and model-provider setup.
- `GET /company/catalog` returns the company hierarchy and agent capabilities.
- `POST /company/ceo/run` is the only user-facing agent entry point.
- `GET /company/sessions/{session_id}/groups` returns company work groups.
- `GET /company/sessions/{session_id}/events` returns the read-only collaboration timeline.
- `GET /company/sessions/{session_id}/stream` streams timeline updates.
- `GET/PUT/DELETE /company/permissions` manages scoped tool permissions.
- `POST /company/approvals/{approval_id}` resolves a pending privileged action.
- `GET /plugins/catalog` reports company tool and connector readiness.
- `/github/*` manages the optional GitHub App connection.

The user speaks only to the CEO. The CEO delegates to directors, and directors
delegate to their own employees. Internal agents cannot be called directly by
the client.

## Required configuration

Use environment variables; do not commit credentials.

- `GEMINI_API_KEY` or `GOOGLE_AI_API_KEY` for the CEO.
- `OPENROUTER_API_KEY` for directors and employees.
- `ARC_BACKEND_API_KEY` is required for remote and production access; use at least 32 characters. Empty-key guest access is restricted to loopback development. Do not embed this key in Flutter. An authenticated access gateway must hold and inject it for public deployments.
- `ARC_ALLOWED_ORIGINS` and `ARC_TRUSTED_HOSTS` in production.

Optional managed connectors use their matching URL and token variables:
`ARC_FINANCE_CONNECTOR_*`, `ARC_CRM_CONNECTOR_*`, and
`ARC_CLOUD_CONNECTOR_*`.

## Safety model

Every request is scoped to a random temporary session capability. Tools are allowlisted per
role and audited. The default global `ask` policy asks for every tool. Global
`allow` is an explicit user choice; narrower per-tool deny/ask/scope rules still
apply. Expired or exhausted grants return to ask, and force-approval requests
cannot be skipped. Queued actions are checked for explicit revocation at execution. Deletions are recoverable, and approval tokens are actor- and
session-bound.

## Tests

```powershell
cd lib/backend
py -m unittest -v test_department_backend.py
```

## No accounts or saved state

Flutter opens directly and sends a random UUID-v4 in `X-Arc-Session`.
Keep this token private; it is a session capability, not a verified identity.
The chat `session_id` in request JSON is separate from this header.

There is no database, disk chat history, or account login. Groups, conversations,
permissions, audit events, approvals, publish jobs, and GitHub connections exist
only in process memory. A server restart clears all of them; restarting or
resetting the app gives it a new temporary identity. Reconnect GitHub after reset.

Run **one Uvicorn worker**. Multiple workers/replicas cannot share this state.
A public unprotected endpoint lets anyone consume your model quota; deploy behind
an authenticated gateway or restrict network access. Approval-required tools still
ask before executing. Model providers receive prompts; no local database does not
mean model providers have no retention. Tool-created files are still real files.

Example PowerShell (local guest mode, backend provider keys already configured):

```powershell
$arcHeaders = @{ "X-Arc-Session" = [guid]::NewGuid().ToString() }
Invoke-RestMethod http://127.0.0.1:8000/company/catalog -Headers $arcHeaders
$arcBody = @{ prompt = "Help plan my company"; session_id = "demo" } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/company/ceo/run -Method Post -Headers $arcHeaders -ContentType "application/json" -Body $arcBody
```

The frontend and backend must be deployed together for the new header contract.
The existing remote Azure deployment is not changed by local file edits.

## Project teams and marketplace

The bundled `company/model_catalog.json` contains the researched model-level
snapshot, generated from the official OpenRouter catalog including all output
modalities. Each entry preserves its exact API model ID, source URL, context,
modalities, tool/reasoning support, and per-million-token rates. Summaries restate
catalog facts and provider focus; department matches are capability-based
suggestions, never benchmark rankings. Pricing excludes possible non-token fees.

`GET /company/marketplace` serves the current cached catalog. Add `?refresh=true`
to refresh it from OpenRouter; a provider failure leaves the cached catalog
available. Flutter bundles the same snapshot for offline discovery. Specialist
image/audio/embedding models remain visible, but ARC only hires models listing
text output and tool calling. `OPENROUTER_API_KEY` enables compatible model
selection and execution by exact model ID, subject to provider availability.
The older `company/marketplace.json` and `ARC_MARKET_*_MODEL` settings are retained
only for compatibility with previously selected session personas.

`GET/PUT /company/sessions/{session_id}/team` reads or replaces a project team.
The mode is `manual` or `ceo`; members contain marketplace `agent_id` and company
`role_id`. A model can fill several roles, but each role has one hire. The CEO
asks for selection preference before delegating and can assemble a configured
team when asked. Delegation uses the selected real model for each role and keeps
the existing reporting chain and tool approvals. Include the department lead
when hiring employees so the CEO can reach them through that lead.

Teams belong to the temporary actor and project session. They survive later
messages and navigation within that app session, and are removed with project
deletion or backend restart. Browsing the marketplace works when the backend is
offline; saving a hire requires the updated backend. No payment is processed.



## Human talent profiles

The marketplace opens with a category choice. Neither the AI directory nor the
human directory loads until selected. The talent profile editor supports a
self-authored headline, summary, skills, availability, USD hourly/project rates,
and volunteer work, with a live preview before publication.

- `GET /company/talent` discovers published profiles across temporary actors.
- `GET /company/talent/profile` loads only the current actor's profile.
- `PUT /company/talent/profile` creates or updates that actor's profile.
- `DELETE /company/talent/profile` removes only that actor's listing.
- `POST /company/talent/{profile_id}/briefs` saves a private project brief.

Published profile fields are intentionally visible to other session owners.
The ownership token is never returned in public profiles. Paused listings are
hidden from discovery. Unavailable or withdrawn profiles cannot receive new
briefs. A brief is a private draft: it sends no message, purchases nothing, and
does not create a contract. There is no payment or messaging integration.

Profiles use the existing in-memory store and one profile per temporary actor.
They survive navigation but are cleared on server restart. Resetting the app's
session removes access to manage its previous profile; this is not an account
system or a persistent production directory. The editor explains this before
publication. Multi-worker hosting still requires shared storage in future work.

For local Flutter browser development, the backend accepts loopback browser
origins if `ARC_ALLOWED_ORIGINS` is empty. For deployed frontends, configure the
exact frontend origins. Local edits do not update the existing Azure service.


## Work-first browsing and your own employees

The collective opens with Research, IT & engineering, Design & creative,
Marketing & sales, Finance & analysis, Operations, and Legal & compliance.
Each area offers AI models, public human talent, and private employees.
The full model directory remains reachable through Browse all AI models or the
All models filter. Model search, tool/reasoning filters, factual comparison of
up to three models, and explicit pagination cover the full catalog.

Public talent profiles include a specialty. Private employees use `/company/humans`
and can carry a summary, skills, specialty, availability, rate, pricing basis,
and project `session_id`. `GET /company/humans?session_id=...` scopes the list to
that project (plus legacy unassigned employees). Adding an employee never
publishes a talent listing or sends an invitation. Prepared employee tasks use
the existing private `/company/human-tasks` draft API. All records still use
session-owned in-memory storage and are cleared when the backend restarts.

## Security changes (2026-10-23)

See `SECURITY_REVIEW_2026-10-23.txt` at the repository root for findings, evidence,
limits, and the outstanding historical credential rotation.

- `ARC_ENVIRONMENT=production` (also detected on Azure via `CONTAINER_APP_NAME`)
  requires a strong backend key. Empty-key sessions only work from loopback in
  development. A shared key is a server-to-gateway secret, never client identity.
  The gateway must authenticate users and bind session capabilities to them.
- The tool workspace setting is now a storage BASE. Each actor and project gets
  its own `.arc/workspaces/<actor hash>/<project hash>` directory. Backend source
  and old shared files are not imported into any user's workspace. Keep the base
  private to the service account and never place host secrets in project files.
- The API never executes terminal commands in its credential-bearing process.
  The optional `services/terminal_gateway.py` runs disposable, networkless
  containers with no host mounts, a read-only system, a non-root user, resource
  limits and a command deadline. `tools/prepare_terminal.py` pins the built image
  and prepares a one-time workspace pairing code. Only bounded private project
  snapshots are copied; hidden paths, secret-bearing files and links are excluded.
  Large files or oversized projects are rejected. Container changes are discarded.
  The gateway validates the paired actor and project identity independently.
  WSL integration settings alone are not a Windows security boundary; this local
  option relies on container restrictions and is not a hardened VM for hostile code.
- All managed gateways also require a token and an actor provisioned in
  `ARC_CONNECTOR_ALLOWED_ACTORS` or explicit one-time local terminal pairing.
  Gateways receive the server-derived actor ID,
  workspace ID, role and session and must authorize every operation/resource.
  An opaque guest capability does not prove a person's identity.
- Request bodies are capped at 1 MB, including chunked uploads, with a 15-second
  upload timeout. Peer and global rate limits cannot be reset by a new session
  UUID. Work requests are capped at 30/peer/minute, 60/global/minute and four
  concurrent requests; streams are capped at four/peer and 64/global. These are
  per-process limits. Keep one worker and add gateway quotas and provider spend
  caps. Already running actions cannot be rolled back by deleting a chat.
- RAM collections have finite capacities; audit and collaboration feeds retain
  bounded recent entries. At capacity new state fails closed. This is temporary
  storage, not a durable public directory. Restart clears state, not tool files.
- The Dockerfile runs as UID 10001, uses the tested dependency lock, excludes local
  environments/secrets, and disables dotenv loading. It has not been built here
  because Docker is unavailable. Rebuild, scan and test the image in CI.
- CI tests security regressions and rejects known credential patterns before
  Azure login/deployment. Build failures stop deployment; actions are pinned to
  verified upstream commit IDs. Review and update pins deliberately.
- `web/_headers` supplies a tested Flutter-compatible policy for hosts supporting
  that format. Configure equivalent HTTP headers on other hosts and update the
  exact API origin when deploying. `_headers` does not configure arbitrary hosts.
- UI errors use app-authored wording; server URLs, input echoes and exception
  details are not displayed. Genuine failures are still reported with retry
  guidance. External GitHub and model-source links are restricted to their
  expected HTTPS origins.

## Working local backend launcher

Run `python tools/run_backend.py` from the repository root (after installing
`lib/backend/requirements.lock`). It binds to 127.0.0.1:8765 and loads the project
`.env` explicitly, overriding stale credentials inherited from the shell. This
is the normal local server; `.arc/security/local_backend.py` is an intentionally
credential-free audit harness and must not be used for normal chat.

The default CEO provider remains `google_ai_studio`. Set `ARC_CEO_PROVIDER` to
`openrouter` plus an exact `ARC_CEO_MODEL` (or `OPENROUTER_MAIN_MODEL`) to use your
configured OpenRouter key. Provider choice is explicit, with no silent fallback.
The catalog and responses report the active provider/model. Placeholder keys do
not count as CEO configuration. `/health/ready` checks the selected CEO provider.
`ARC_CEO_MAX_OUTPUT_TOKENS` defaults to 1024 and `ARC_AGENT_MAX_OUTPUT_TOKENS` to
4096; both are clamped to 64..4096. The CEO receives candidate models only when
assembling a team in CEO selection mode. A provider credit limit can still block
requests; it is not converted into a fabricated answer.

On 2026-10-23 the local server was verified with a real provider-backed CEO
response. The old shell credential was rejected; the different project `.env`
credential authenticated successfully. Credential values were not logged.

## Agent communication privacy

The CEO and every employee share a rule keeping ARC platform implementation out
of their responses. Explicit platform-internals requests receive a local policy
notice without invoking a model or delegating. Known internal identifiers,
locations and credential values are checked at the outgoing text boundary;
CEO replies, employee reports, generated group objectives and timeline content
use that boundary. User-authored messages remain visible as authored. Normal
architecture advice for the user's own project remains available. The public
agent catalog no longer publishes model environment-variable names.

These are product communication controls and defense in depth, not a claim that
regex filters prevent every possible disclosure or replace authorization and
workspace isolation. Keep actual infrastructure credentials out of model inputs.
