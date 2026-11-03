# Security

Keep provider API keys, workspace access capabilities, human invitation links,
terminal service tokens, private project data, and provider vault files out of
issues, screenshots, and commits. `.env`, `secrets/`, `.arc/`, local runtimes, and
build outputs are intentionally excluded from source control.

Run `python tools/check_source_secrets.py` before committing. The scanner is a
useful check, not a guarantee that a repository contains no sensitive data. If a
credential is exposed, revoke it with its provider and inspect account usage;
removing it from a new commit does not revoke it or erase older copies.

Production requires a strong backend access key held by the server-side proxy.
Never compile that key into Flutter. Browser workspace access uses a random
capability rather than a verified user account. Shared browser profiles can open
saved workspaces. Do not use the hackathon deployment for sensitive production
records without appropriate identity and access controls.

Terminal jobs run in disposable restricted containers. The private Docker broker
is an administrative component; do not expose it or its socket publicly. Treat
container isolation as defense in depth, not a guarantee against hostile code or
kernel vulnerabilities. Model calls and project file tools run in the control
layer; this project does not claim every tool action is sandboxed.

To report an issue, use this repository's private vulnerability reporting option
if available. Do not post exploit details or credentials in a public issue.
Deployment and containment details are in `deploy/vultr/README.md` and
`docs/VULTR.md`.
