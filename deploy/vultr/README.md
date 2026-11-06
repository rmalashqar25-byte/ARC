# Deploy ARC on Vultr

This deployment runs the Flutter application, Python backend, durable company queue,
encrypted provider vault, and restricted terminal broker on one Ubuntu 24.04 VM.
It does not create or purchase Vultr resources by itself.

## Prepare locally

```powershell
flutter build web --release --no-pub --no-web-resources-cdn --dart-define=ARC_API_BASE_URL=/api --output=.arc/vultr/web
python tools/package_vultr.py
```

The release archive is `.arc/vultr/arc-release.tar.gz`. The packager uses an explicit
source allowlist and scans credential patterns. It excludes `.env`, Git history,
the local provider vault, browser workspace credentials, databases, media, tests,
and local terminal configuration. The archive includes a SHA-256 manifest.

## Provision and install

Use the hackathon credit balance and approve the displayed server price before
provisioning. A small x86 VM with at least 2 GiB RAM is a starting point; do not
install a local LLM on that VM. Select Ubuntu 24.04, a dedicated SSH public key,
and the supplied `cloud-init.yaml`. Keep only TCP 80/443 public; restrict SSH to
the administrator's IP in the Vultr firewall. Do not expose 8000 or 8768.

Point a public hostname's A record to the server. If using an existing hostname,
check ownership and existing DNS records before changing anything.

Upload the release with SCP, verify its SHA-256, extract it into a new release
directory such as `/opt/arc/releases/2026-11-03`, and run as root:

```sh
cloud-init status --wait
cd /opt/arc/releases/2026-11-03
bash deploy/vultr/install.sh arc.example.com
```

The hostname must resolve to this VM, and ports 80/443 must be reachable for the
public certificate. The installer creates server keys locally, preserves them on
updates, builds the execution image, validates Compose/Caddy, and starts services.
Only Caddy listens publicly; the backend and terminal bind to loopback.

The application opens at `https://arc.example.com/`. Its API is under `/api/` on
the same origin. Caddy inserts the private backend key; it is never compiled into
the browser application. API schema and detailed readiness routes are private.

## Model connection

No local developer API keys are copied. Open ARC settings and save an approved
provider connection for the demo workspace. That connection serves the CEO and
all company roles. A remote deployment cannot use Ollama on a visitor's computer
through server localhost. Use a supported remote HTTPS provider there.

For the **Powering the Future of Work** track, Vultr Compute powers orchestration;
Vultr Serverless Inference is optional. For **Blast Radius Zero**, the judged
deployment must additionally enforce Vultr inference for all agent model calls
and isolate all relevant agent execution. This recipe alone does not enforce
that track restriction or claim full Challenge 1 compliance.

Keep `/etc/arc/provider.env` empty for a BYOK demo. Shared provider credentials
would let public visitors consume that shared account's quota; protect access and
set provider-side limits before enabling any shared service. Public workspace
access currently uses random capabilities rather than verified user accounts.

## Terminal access

The broker has Docker access and must be treated as a privileged administrative
service. It receives no model credentials and listens only on loopback. Neither
the backend nor execution containers receive the Docker socket. Each check uses
a fresh non-root container, no network or host mounts, a read-only root, dropped
capabilities, time/output caps, 256 MiB memory, one CPU, and 64 PIDs.

New public workspaces are not automatically granted this server's terminal.
After verifying the intended browser workspace and approving its connection, the
server administrator can run:

```sh
python3 deploy/vultr/connect_workspace.py WORKSPACE-UUID-V4
```

This preserves the single-workspace grant and refuses to silently replace an
existing workspace. Never publish that workspace capability or use it as a demo
screenshot. Existing per-tool restrictions and explicit denials still apply.

## Verify the real deployment

```sh
curl --fail https://arc.example.com/api/health/live
docker compose --env-file /etc/arc/deployment.env -f deploy/vultr/compose.yaml ps
ss -ltn
```

Also check the app in a new browser session, save a real provider connection, run
a bounded job, inspect its actual test output, restart the backend, and verify
saved company state. Confirm external connections to 8000/8768 fail. Run the
isolation and timeout demonstration on the VM before claiming Vultr containment.

Do not use `docker compose config` without `--quiet` in public logs; resolved
configuration contains private server keys. Avoid sharing raw container inspect
output. Check deployment logs for credentials before publishing evidence.

## Persistence, updates, and shutdown

Data stays in `/var/lib/arc` and secrets in `/etc/arc`, outside release directories.
Back up both privately, including the provider vault encryption key; test restore.
Use SQLite's backup API or stop the backend while copying the database.

For updates, upload into a new release directory and run the installer there. It
preserves data and grants. Retain the previous release for rollback. This is a
single-instance deployment and updates can briefly interrupt service.

Pause company work in ARC before maintenance. To stop this release:

```sh
docker compose --env-file /etc/arc/deployment.env -f deploy/vultr/compose.yaml down
```

Stopping containers or powering off a VM does not necessarily stop cloud billing.
Review Vultr resources and credit expiry after the hackathon. Destroy resources
only after making and verifying any needed backups.

References: [Vultr provisioning](https://docs.vultr.com/products/compute/instances/cloud-compute/provisioning),
[Docker Compose services](https://docs.docker.com/reference/compose-file/services/),
[Caddy reverse proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy),
[official hackathon requirements](https://lablab.ai/ai-hackathons/vultr-hackathon).

## Optional public demo media

`/demo/` serves intentionally published files from `/var/lib/arc/public-media`, mounted read-only only in Caddy. Place the player, MP4s, posters and presentation PDF there with public read permissions. This directory persists across app releases and is separate from private state, provider keys and workspace files. Directory browsing is disabled; missing media paths return 404. Never copy private recordings or credentials into this directory. The standard app build does not bundle promotional media.
