# ARC

[MIT licensed](LICENSE) · [Live demo](https://arc.64.177.59.174.sslip.io/) · [Judge walkthrough](docs/JUDGES.md) · [Hackathon audit](docs/HACKATHON.md)

![ARC: a company workspace for real work](docs/assets/arc-hackathon-cover.png)

## Vultr deployment

**Live demo: [Open ARC](https://arc.64.177.59.174.sslip.io/)**. ARC was deployed on **5 November 2026** to Vultr Compute in **Atlanta**, using an Ubuntu 24.04 VM with 2 vCPUs and 4 GB RAM. The deployment includes the Flutter web app, Python control layer, persistent company queue, encrypted provider vault, HTTPS proxy, and Linux terminal broker.

The services used, deployment architecture, execution workflow, containment checks, and reproduction steps are documented in **[ARC on Vultr](docs/VULTR.md)**. The running server passed HTTPS/API checks and five real terminal isolation and timeout checks. Vultr Serverless Inference is not used. The organizer's online build dates are 3-8 November 2026; see the [official event page](https://lablab.ai/ai-hackathons/vultr-hackathon).

**[Vultr installation guide](deploy/vultr/README.md)** includes the production configuration, release packaging, HTTPS setup, persistent storage, and private execution service. Build web with `--dart-define=ARC_API_BASE_URL=/api` for this deployment. No developer credentials or local company data are included in a release.

A company workspace for developing an idea, assembling a team, and following its work.

## Who ARC helps

A small founder-led team often loses work between chats, specialists, and freelancers. ARC gives the founder one CEO conversation, manager-owned assignments, a quiet queue, and a restricted job portal for human employees. People see their assigned work rather than internal agent conversations. Human capacity prevents over-allocation. A scheduler checks for actual work every five seconds without spending model tokens while idle.

The initial use case is a small product team shipping bounded fixes and reviewing contractor deliverables. Potential revenue is a hosted workspace subscription with bring-your-own model keys; payments, customer pilots and revenue are not implemented or claimed. Marketplace prices are illustrations, not provider subscriptions. The next validation is a small founder-team pilot measuring task completion, intervention rate and cost per verified job.

## Open-source licensing and provenance

ARC's original source and documentation are [MIT licensed](LICENSE). Preserve the license and [third-party notices](THIRD_PARTY_NOTICES.md) when redistributing. The running app exposes Flutter's generated license bundle in Workspace settings. API providers and hosted models retain their own service terms; model weights are not bundled.

ARC existed before this event. [PROVENANCE.md](PROVENANCE.md) distinguishes that foundation from the Vultr deployment and reliability work completed during the hackathon. The public repository's initial import date is not a claim that all code was newly written then.

## Project layout

- `lib/frontend/`: chat, marketplace, team activity, and workspace settings.
- `lib/backend/`: company orchestration, tools, integrations, and session isolation.
- `web/`: browser entry point, opening animation, and app metadata.
- `android/` and `windows/`: platform applications.
- `assets/`: application images and animations.
- `test/`: Flutter and opening animation checks.
- `tools/`: local launch and source checks.

## Run locally

Install Flutter dependencies with `flutter pub get`. Install the Python backend dependencies from `lib/backend/requirements.lock`, then copy `.env.example` to `.env` and configure the required providers.

Use a Python 3.13 virtual environment for the backend: `python -m venv .venv`, activate it, and run `python -m pip install -r lib/backend/requirements.lock`. Run the Python commands below from that environment.

Start the backend with `python tools/run_backend.py`. Start the web app with `flutter run -d chrome --dart-define=ARC_API_BASE_URL=http://127.0.0.1:8765`.

For faster browser startup, use `python tools/run_web.py --build` and open `http://127.0.0.1:8766/`. This builds an optimized app and serves its rendering assets locally. Subsequent launches only need `python tools/run_web.py`; rebuild after source changes. The development command above includes a debug compiler and takes longer to start.

ARC opens directly into the workspace. Workspace access and the active company are saved on this browser. Anyone using the same browser profile can reopen that company; provider API keys stay on the server. If browser storage is unavailable, access remains temporary. The local launcher saves company records, teams, and jobs in an ignored local recovery database. Resetting the session pauses its company workers and replaces the browser’s saved access with a fresh workspace. Integration permissions and agent action approvals remain available in settings.

## Checks

- `flutter test`
- `flutter analyze`
- `node --test test/arc_intro_test.cjs test/arc_startup_test.cjs`
- `python -m unittest discover -s lib/backend -p "test_*.py" -q`
- `python -m unittest discover -s tools -p "test_*.py" -q`
- `python tools/check_source_secrets.py`

The credential check includes new, non-ignored source files. Use `--staged` to check the exact staged contents before a commit. Keep `.env`, `secrets/`, local runtimes and build output private. GitHub checks validate source on pushes and pull requests. The Vultr deployment recipe never purchases or provisions cloud resources automatically.

Backend configuration and deployment details are documented in `lib/backend/COMPANY_BACKEND.md`.

The promotional video, captions, player, and production sources are kept outside the app in `../ARC-media/arc-promo/`. They are separate from the website's opening animation in `web/`.

## Optional local terminal

The terminal runs approved Git, search, and Python/pytest commands on temporary project copies. It requires no cloud subscription. On Windows, prepare it with `python tools/setup_terminal_runtime.py`, `powershell -File tools/start_terminal_engine.ps1`, and `python tools/prepare_terminal.py`. Start `python services/terminal_gateway.py` and the ARC local backend launcher. Opening ARC automatically connects the eligible local workspace without typing a setup code. An existing terminal owner remains protected; remote deployments retain explicit pairing. Keep `.arc/terminal-runtime/` private.

Each command uses a disposable container with no network or host mounts, a read-only system, a non-root user, resource limits, and a time limit. Container test changes are discarded. WSL integration settings are convenience settings, not a Windows security boundary; this runtime relies on container restrictions. Do not treat it as a hardened virtual machine for hostile workloads.

If a new temporary workspace needs pairing, `python tools/prepare_terminal_connection.py` prepares a fresh one-time code without rebuilding the image. Refresh Agent tools after starting the local services.

## Continuous company work

Open **Company workspace → Open company work board**. Choose a configured compatible model, review its pricing, allow automatic local project work, and start the company worker. A deterministic scheduler checks the saved queue every five seconds; it is not an additional AI agent. The selected planning/review model is invoked for user chat, a planning job, or a submitted review. **Save model choice** changes that choice without starting the scheduler; pausing does not switch the CEO to another model. An empty queue makes no model requests and creates no activity messages. Work continues when the browser closes, while the local backend and computer remain on. The local launcher also checks the already installed terminal service and restarts it if needed.

The private SQLite database defaults to `.arc/company.sqlite3`. Queue leases recover interrupted jobs; conversation memory, teams, groups, and human records survive backend restarts. Explicit tool restrictions remain restrictive after recovery; one-time execution approvals are not restored. Keep one backend process and preserve the database and project workspace directories. An ephemeral hosting filesystem needs an administrator-configured persistent volume for recovery.

Continuous mode supports configured compatible models, including paid and free options. Paid models require explicit pricing confirmation. The selected model’s input/output token rates become the ceilings for automatic team selection and model calls; higher or unknown rates are blocked until confirmed. There is no silent paid-model fallback. At most 36 model requests are allowed per company per UTC day; this request limit is not a dollar spending cap. Provider charges apply to the chosen models. Free-only verification is separate from user model selection. Local autonomy covers project reads/updates, drafts, calculations, delegation, and restricted terminal commands. External publishing, financial connectors, cloud operations and file deletion remain outside that automatic scope. A task marked **Require a passing terminal check** is not completed without an actual successful command. Plans waiting on delegated work remain open until their team tasks finish. Delegation is saved even while the scheduler is paused, and chat returns an honest queued receipt rather than waiting for nested agents. Step-limit failures become blocked jobs, never completed work or misleading connection errors.

Humans have a maximum job capacity of 0–20, including pending offers. Their private invitation link opens only their assigned groups, briefs, deliverables, and supervisor feedback. It never exposes internal conversations or an agent chat. They accept or decline a job and submit a deliverable to the selected manager. Submissions queue a manager review; the founder can review submitted work directly. Links expire after seven days and can be replaced or revoked. Paid terms must be agreed separately. Share links directly with the intended person; the local loopback preview is accessible only on this computer.

Set `ARC_COMPANY_WORKER_ENABLED=1` for an independently launched server; the local launcher enables it automatically. `ARC_COMPANY_DB` can select a different private database path. `python tools/verify_free_agent.py --background --model <exact-model-id:free>` verifies an actual coding task through the queue without changing the running app's approvals.

## Live free-model check

`python tools/verify_free_agent.py --model <exact-model-id:free>` runs a real CEO-to-engineering task on disposable example files using the already paired local terminal. It verifies zero current catalog prices, blocks model fallbacks, and checks that an agent changes the implementation and passes an independently rerun test. It never changes the running app's model or approval settings. Its private report is saved under `.arc/security/`.

Use a tool-capable free model with optional reasoning. The check disables reasoning for this small task so the response budget is available for the result. For normal app configuration, optional `ARC_CEO_REASONING` and `ARC_AGENT_REASONING` accept `off`, `minimal`, `low`, `medium`, or `high`; leave them unset to retain the provider default. Use `off` only with models that support disabling reasoning.


### Developer model connections

Open **Workspace settings → Developer connections** to replace ARC's default API
with your own connection. There is one active connection per workspace. Choose
OpenAI, OpenRouter, Gemini, Ollama, or a custom OpenAI-compatible Chat Completions API.
Use **Load available models**, then choose a model by name from the searchable
list. No model ID needs to be typed. Model discovery lists models; it does not
generate a billable completion. Custom providers must support the model-list API.

The selected connection is used by the CEO and all company roles, including queued
work and reviews. Existing role assignments use the newly selected model. Saving
or removing a connection pauses company work. Start it again from Company work
when ready. Removing a connection returns new chats to the server's default API.
A provider failure never silently falls back to ARC's API key.

Keys are encrypted in `.arc/provider-vault/connections.sqlite3` and are never
returned through the API, saved in browser storage, or included in agent prompts.
On Windows, the vault encryption key is protected with the current user's DPAPI;
on other systems the key file has owner-only permissions. Keep the vault private,
exclude it from source control, and back it up with the appropriate server-user
recovery procedure. `ARC_PROVIDER_VAULT` can select a private persistent directory.
A lost vault key makes stored connections unusable; users must enter their keys
again. Public deployments need HTTPS and a persistent, private vault volume.

Remote connections require HTTPS on port 443. Requests pin validated public DNS
addresses, block private/reserved destinations, ignore proxy environment variables,
and never follow redirects. Local model access is enabled only by the local
launcher outside production. Supported local bases are `/v1` on loopback ports
11434 (Ollama), 1234 (LM Studio), or 8080 (llama.cpp). A cloud backend cannot reach
Ollama on a visitor's computer. Install and start the model server separately;
ARC does not download model weights automatically. Tool calling must be supported
by the chosen model and enabled in Developer connections. Provider-owned rates
are not represented as zero-cost when the price is unknown. Automatic work keeps
the existing 36 model requests per company per UTC day limit.

The local launcher starts the already-installed terminal service. Opening ARC
connects its local workspace without entering a pairing code. An existing terminal
owner remains bound to that workspace: another workspace cannot claim it. The
terminal keeps its isolated temporary project copies, restricted command policy,
network isolation, and explicit tool denials. Connected terminal commands do not
need per-command approval; other tools retain their approval policy. Set
`ARC_TERMINAL_AUTO_CONNECT=0` before launching to disable automatic first pairing.
Remote deployments retain explicit terminal pairing.

Compatibility references: [Ollama](https://docs.ollama.com/api/openai-compatibility),
[Gemini](https://ai.google.dev/gemini-api/docs/openai/), and
[OpenRouter](https://openrouter.ai/docs/api_reference/authentication).


To verify developer API routing against an actual free provider model, run
`python tools/verify_developer_connection.py` after installing backend dependencies
and configuring the local OpenRouter key. The check authenticates the key, saves
and restores a connection in a temporary vault, obtains a real CEO reply, and runs
an actual calculator tool from a queued agent task. It rejects invalid keys and
checks isolation between workspaces. It only permits the exact free model with
verified zero pricing, records provider costs, and does not alter the live app's
company or provider settings. The private result is saved in
`.arc/security/developer-api-verification.json`. Saving a developer connection now
checks authentication and the selected model's availability before replacing it.


Direct provider connections are handled in `lib/backend/developer_connections.py`:
OpenAI uses `https://api.openai.com/v1`, Gemini uses its official OpenAI-compatible
endpoint, and Ollama uses `http://127.0.0.1:11434/v1` from the local launcher.
Users choose the provider and load its available models; no custom URL is required
for these providers. OpenAI requests use `max_completion_tokens`, while Gemini,
Ollama, and existing compatible services keep their supported `max_tokens` field.
See the [OpenAI Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).
