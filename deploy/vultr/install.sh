#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ $(id -u) -ne 0 ]]; then
  echo "Run as root on the ARC server." >&2
  exit 1
fi
if [[ $# -ne 1 ]] || [[ ! $1 =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ ]] || [[ $1 != *.* ]]; then
  echo "Usage: bash deploy/vultr/install.sh arc.example.com" >&2
  exit 1
fi
release_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
if [[ ! -f "$release_root/web-build/index.html" ]]; then
  echo "Use the prepared release bundle, including web-build/." >&2
  exit 1
fi
command -v docker >/dev/null
docker compose version >/dev/null
systemctl enable --now docker
install -d -m 700 /etc/arc /var/lib/arc
# Explicitly public, separately mounted media; never mount private state here.
install -d -m 755 /var/lib/arc/public-media
install -d -m 700 -o 10001 -g 10001 /var/lib/arc/data /var/lib/arc/data/projects /var/lib/arc/data/state
# The backend owns grant updates; the capability-free root broker reads group 0.
# Setgid keeps atomically replaced grant files in the broker's read group.
install -d -m 2750 -o 10001 -g 0 /var/lib/arc/terminal
install -d -m 700 /var/lib/arc/caddy /var/lib/arc/caddy/data /var/lib/arc/caddy/config
if [[ ! -e /etc/arc/provider.env ]]; then
  printf '%s\n' '# Provider credentials stay here or in each workspace encrypted vault.' > /etc/arc/provider.env
fi
chmod 600 /etc/arc/provider.env

docker build --tag arc-terminal:release "$release_root/services/terminal"
python3 - "$1" <<'PY'
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

path = Path('/etc/arc/deployment.env')
settings = {}
if path.exists():
    settings = dict(line.split('=', 1) for line in path.read_text().splitlines() if '=' in line and not line.startswith('#'))
if settings.get('ARC_PUBLIC_HOST') not in (None, sys.argv[1]):
    raise SystemExit('Hostname differs from the existing deployment; update it deliberately first.')
settings.update(ARC_PUBLIC_HOST=sys.argv[1], ARC_DATA_ROOT='/var/lib/arc')
for name in ('ARC_BACKEND_API_KEY', 'ARC_TERMINAL_RUNNER_TOKEN'):
    settings.setdefault(name, secrets.token_hex(32))
path.write_text(''.join(f'{key}={value}\n' for key, value in settings.items()))
path.chmod(0o600)
image = subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{.Id}}', 'arc-terminal:release'], text=True).strip()
gateway = Path('/etc/arc/terminal-gateway.json')
gateway.write_text(json.dumps({'engine': 'linux', 'image_id': image, 'token': settings['ARC_TERMINAL_RUNNER_TOKEN'], 'grants_file': '/terminal/grants.json'}))
gateway.chmod(0o600)
grants = Path('/var/lib/arc/terminal/grants.json')
if not grants.exists():
    grants.write_text(json.dumps({'actors': [], 'paired': False}))
os.chown(grants, 10001, 0)
grants.chmod(0o640)
PY

compose=(docker compose --env-file /etc/arc/deployment.env --file "$release_root/deploy/vultr/compose.yaml")
"${compose[@]}" config --quiet
"${compose[@]}" build
"${compose[@]}" run --rm --no-deps web caddy validate --config /etc/caddy/Caddyfile
"${compose[@]}" up --detach --wait --wait-timeout 180
"${compose[@]}" ps
printf '\nARC started. Verify HTTPS at https://%s/ and /api/health/live.\n' "$1"
echo 'Model replies require a saved provider connection. No personal keys were copied.'
