"""Explicit free-model coding requests and repository-scoped artifact delivery."""

import base64
import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path

import httpx
from agent_store import get_agent_store
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

LOG = logging.getLogger("uvicorn.error")


def repository_for(actor):
    repository = os.getenv("ARC_GITHUB_REPOSITORY", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        return None
    owner = repository.split("/")[0].casefold()
    for item in get_agent_store().list_github_connections(actor):
        if item.get("account_login", "").casefold() == owner and item.get(
            "github_user_id"
        ):
            return repository, item["installation_id"]
    return None


async def execution_request(prompt, messages, actor, session, database):
    from developer_connections import DEVELOPER_ACTOR

    token = DEVELOPER_ACTOR.set(actor)
    try:
        return await _execution_request(prompt, messages, actor, session, database)
    finally:
        DEVELOPER_ACTOR.reset(token)


async def _execution_request(prompt, messages, actor, session, database):
    from developer_connections import connection
    from terminal_connection import terminal_is_connected

    from company.model_catalog import catalog, refresh_catalog
    from company.team import get_team, marketplace, save_team
    from company.work_policy import WORK_SCOPE, model_prices

    if database is None or WORK_SCOPE.get() is not None:
        return None
    text = " ".join(prompt.lower().split())
    tasks = database.list(actor, session)
    intent = get_agent_store().load_session(actor, "execution_request", session) or {}
    code = bool(
        re.search(r"\b(build|create|make|implement)\b", text)
        and re.search(
            r"\b(calculator|calculter|calcluter|app|website|software|project)\b", text
        )
    )
    nudge = bool(
        (tasks or intent.get("pending"))
        and len(text.split()) <= 18
        and any(
            w in text
            for w in ("choose", "start", "continue", "do it", "go ahead", "retry")
        )
    )
    status = bool(
        (tasks or intent.get("pending"))
        and len(text.split()) <= 10
        and any(
            w in text
            for w in ("push it", "pushed", "status", "is it done", "any updates")
        )
    )
    if not (code or nudge or status):
        return None
    latest = next(
        (t for t in tasks if t.get("parent") is None and t["kind"] == "agent"), None
    )
    if status:
        if latest is None:
            return {
                "message": "Not pushed. Your saved request is waiting for this workspace's GitHub and terminal connection.",
                "response_kind": "connection_required",
            }
        receipt = latest.get("delivery", {})
        message = (
            ("Pushed to GitHub: " + receipt["url"] + "\nCommit SHA: " + receipt["sha"])
            if receipt.get("sha")
            else (
                "Not pushed yet. Task status: "
                + latest["status"]
                + ". "
                + (latest.get("result") or "The assignment has not finished.")
            )
        )
        return {
            "message": message,
            "response_kind": "work_status",
            "work_task_id": latest["id"],
        }
    # A follow-up resumes the original user brief; it does not create another plan.
    briefs = [
        m["content"]
        for m in messages
        if m.get("role") == "user"
        and re.search(
            r"\b(build|create|make|implement)\b", m.get("content", "").lower()
        )
        and re.search(
            r"\b(calculator|calculter|calcluter|app|website|software|project)\b",
            m.get("content", "").lower(),
        )
    ]
    brief = (
        prompt
        if code
        else (
            briefs[-1]
            if briefs
            else intent.get("brief") or (latest["description"] if latest else "")
        )
    )
    if not brief:
        return None
    await refresh_catalog()
    own = connection(actor)
    entries = {m["model_id"]: m for m in catalog()}
    candidates = [
        m
        for m in marketplace()
        if m.get("configured")
        and m.get("agent_compatible")
        and model_prices(entries.get(m["model_id"], m)) == (0, 0)
    ]
    if own and not own.get("local") and own.get("provider") != "openrouter":
        candidates = []
    if own and own.get("local") and own.get("supports_tools", True):
        candidates = [m for m in marketplace() if m.get("configured")]
    team = get_team(actor, session)
    preferred = next(
        (m["agent_id"] for m in team["members"] if m["role_id"] == "cto"),
        os.getenv("OPENROUTER_MAIN_MODEL", ""),
    )
    selected = next((m for m in candidates if m["id"] == preferred), None)
    selected = (
        selected
        or next(
            (m for m in candidates if m["id"] == os.getenv("OPENROUTER_MAIN_MODEL")),
            None,
        )
        or next(iter(candidates), None)
    )
    if selected is None:
        return {
            "message": "No tool-capable model with verified zero pricing is available for this connection. No paid model was called.",
            "response_kind": "work_blocked",
        }
    if team["mode"] != "manual" or "choose" in text or "choose" in brief.lower():
        team = save_team(
            actor,
            session,
            "ceo",
            [
                {"agent_id": selected["id"], "role_id": r}
                for r in ("cto", "app_developer")
            ],
        )
    elif not all(
        any(m["role_id"] == r for m in team["members"])
        for r in ("cto", "app_developer")
    ):
        return {
            "message": "This coding task needs a CTO and developer. Ask me to choose them or add them to your team.",
            "response_kind": "work_blocked",
        }
    LOG.info(
        "ARC execution stage=team_saved project=%s roles=cto,app_developer", session
    )
    wants_push = "push" in brief.lower() and any(
        w in brief.lower().replace(" ", "") for w in ("github", "git")
    )
    target = repository_for(actor) if wants_push else None
    get_agent_store().save_session(
        actor,
        "execution_request",
        session,
        {"brief": brief, "pending": True, "requested_at": time.time()},
    )
    if wants_push and not target:
        LOG.warning(
            "ARC execution stage=blocked project=%s reason=github_connection_missing",
            session,
        )
        return {
            "message": "Your CTO and developer are saved. GitHub is not connected to this browser workspace. Open Plugins → GitHub → Connect once; Your saved build request will resume after connecting. I cannot push using another workspace’s connection.",
            "response_kind": "connection_required",
        }
    if not terminal_is_connected(actor):
        LOG.warning(
            "ARC execution stage=blocked project=%s reason=terminal_connection_missing",
            session,
        )
        return {
            "message": "Your team is saved, but this browser workspace has no execution connection. Connect GitHub in Plugins to restore your verified account’s terminal, Your saved request will resume after connecting. No work or push has been claimed.",
            "response_kind": "connection_required",
        }
    if os.getenv("ARC_COMPANY_WORKER_ENABLED", "").lower() not in {"1", "true"}:
        return {
            "message": "The company worker service is disabled. No task was started.",
            "response_kind": "work_blocked",
        }
    active = [
        t
        for t in tasks
        if t["status"] in {"queued", "running", "waiting_team"}
        and t.get("parent") is None
        and t["assignee"] == "cto"
    ]
    calculator = bool(re.search(r"calc(?:ulator|ulter|luter|lcuter)", brief.lower()))
    matching = [
        t
        for t in active
        if not code
        or (calculator and "calc" in t["description"].lower())
        or t["description"].strip().lower() == brief.strip().lower()
    ]
    if matching:
        task = matching[0]
        for duplicate in matching[1:]:
            if duplicate["status"] == "queued" and calculator:
                database.update(
                    actor,
                    session,
                    duplicate["id"],
                    status="blocked",
                    result="Duplicate calculator assignment superseded by "
                    + task["id"],
                    allowed={"queued"},
                )
    else:
        task = database.create(
            actor,
            session,
            title="Build project and deliver files",
            description=brief[:7000],
            assignee="cto",
            requires_check=True,
            dedupe="execute:"
            + hashlib.sha256(brief.strip().lower().encode()).hexdigest(),
        )
    if task["status"] == "completed":
        receipt = task.get("delivery", {})
        return {
            "message": "This assignment is already completed. "
            + receipt.get("url", task.get("result", "")),
            "response_kind": "work_status",
            "work_task_id": task["id"],
        }
    if task["status"] in {"running", "waiting_team"}:
        database.configure(actor, session, True, selected["model_id"])
        return {
            "message": "This assignment is already processing. No duplicate job was created.",
            "response_kind": "work_status",
            "work_task_id": task["id"],
        }
    if task["status"] == "blocked":
        if "retry" not in text and "choose" not in text:
            return {
                "message": "This assignment is blocked: "
                + task.get("result", "")
                + " Say retry after correcting the blocker.",
                "response_kind": "work_blocked",
                "work_task_id": task["id"],
            }
        database.update(
            actor,
            session,
            task["id"],
            status="queued",
            result="",
            allowed={"blocked"},
            reset_attempts=True,
        )
    database.execution_metadata(
        actor, session, task["id"], repository=target[0] if target else None
    )
    # Exact repeat requests reuse one root; subordinate work stays in the same job.
    database.configure(actor, session, True, selected["model_id"])
    get_agent_store().save_session(
        actor,
        "execution_request",
        session,
        {"brief": brief, "pending": False, "task_id": task["id"]},
    )
    LOG.info(
        "ARC execution stage=queued task=%s project=%s free_model=%s",
        task["id"],
        session,
        selected["model_id"],
    )
    return {
        "message": "CTO and developer saved. Automatic work is now enabled and one assignment is queued. "
        + (
            "After the files are created and checked, I will push them to a project branch and report the actual GitHub commit SHA."
            if target
            else "I will report the actual result or a specific blocker."
        ),
        "response_kind": "work_started",
        "work_task_id": task["id"],
    }


def _jwt():
    def enc(value):
        return base64.urlsafe_b64encode(value).rstrip(b"=")

    now = int(time.time())
    head = enc(b'{"alg":"RS256","typ":"JWT"}')
    body = enc(
        json.dumps(
            {"iat": now - 60, "exp": now + 540, "iss": os.environ["GITHUB_APP_ID"]}
        ).encode()
    )
    key_text = os.getenv("GITHUB_PRIVATE_KEY")
    raw = (
        key_text.encode()
        if key_text
        else Path(os.environ["GITHUB_PRIVATE_KEY_PATH"]).read_bytes()
    )
    key = serialization.load_pem_private_key(raw, password=None)
    unsigned = head + b"." + body
    return (
        unsigned + b"." + enc(key.sign(unsigned, padding.PKCS1v15(), hashes.SHA256()))
    ).decode()


async def publish_project(task):
    from agent_tools import _is_sensitive_path, _workspace_root

    database = get_agent_store().work_store
    if (
        database is None
        or not database.company(task["actor"], task["session"])["enabled"]
    ):
        raise ValueError("Company work was paused before GitHub delivery")
    target = repository_for(task["actor"])
    if not target or target[0] != task.get("publish_repository"):
        raise ValueError("GitHub is not connected to this workspace and repository")
    repository, installation = target
    permission = get_agent_store().get_permission(
        task["actor"], "cto", task["session"], "git_publish"
    )
    if permission and permission.get("mode") == "deny":
        raise ValueError("GitHub publishing was explicitly denied for this project")
    root = _workspace_root(task["actor"], task["session"])
    files = []
    size = 0
    secret = re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{35}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}"
    )
    prefix = (
        "projects/" + hashlib.sha256(task["session"].encode()).hexdigest()[:16] + "/"
    )
    branch = (
        "arc/work-"
        + hashlib.sha256((task["actor"] + task["id"]).encode()).hexdigest()[:20]
    )
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(
            p.startswith(".") or p in {"__pycache__", "node_modules", "venv"}
            for p in rel.parts
        ) or _is_sensitive_path(rel):
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Project contains an unsafe symbolic link")
        if not path.is_file():
            continue
        if path.suffix.lower() not in {
            ".html",
            ".css",
            ".js",
            ".ts",
            ".json",
            ".md",
            ".py",
            ".txt",
            ".svg",
        }:
            continue
        raw = path.read_bytes()
        size += len(raw)
        if len(raw) > 500000 or size > 2000000 or len(files) >= 60:
            raise ValueError("Project exceeds bounded GitHub delivery size")
        content = raw.decode("utf-8")
        if secret.search(content):
            raise ValueError("A possible credential was found; publishing stopped")
        files.append(
            {
                "path": prefix + rel.as_posix(),
                "mode": "100644",
                "type": "blob",
                "content": content,
            }
        )
    if not any(
        Path(f["path"]).suffix in {".html", ".js", ".ts", ".py"}
        and not Path(f["path"]).name.startswith("test_")
        for f in files
    ):
        raise ValueError("No application source files were created; nothing was pushed")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ARC-Delivery",
    }
    token = None
    async with httpx.AsyncClient(timeout=25, follow_redirects=False) as client:

        async def request(method, url, payload=None):
            response = await client.request(
                method, "https://api.github.com" + url, headers=headers, json=payload
            )
            if response.status_code >= 400:
                raise ValueError(
                    f"GitHub delivery failed at {method} {url.split('/git/')[-1]} (HTTP {response.status_code})"
                )
            return response.json() if response.content else {}

        try:
            headers["Authorization"] = "Bearer " + _jwt()
            grant = await request(
                "POST",
                f"/app/installations/{installation}/access_tokens",
                {
                    "repositories": [repository.split("/")[1]],
                    "permissions": {"contents": "write"},
                },
            )
            token = grant["token"]
            headers["Authorization"] = "Bearer " + token
            base = "/repos/" + repository
            ref_response = await client.get(
                "https://api.github.com" + base + "/git/ref/heads/" + branch,
                headers=headers,
            )
            exists = ref_response.status_code == 200
            if not exists and ref_response.status_code != 404:
                raise ValueError("Cannot inspect the GitHub project branch")
            if exists:
                parent = ref_response.json()["object"]["sha"]
            else:
                repo = await request("GET", base)
                parent = (
                    await request(
                        "GET", base + "/git/ref/heads/" + repo["default_branch"]
                    )
                )["object"]["sha"]
            commit = await request("GET", base + "/git/commits/" + parent)
            tree = await request(
                "POST",
                base + "/git/trees",
                {"base_tree": commit["tree"]["sha"], "tree": files},
            )
            created = await request(
                "POST",
                base + "/git/commits",
                {
                    "message": "ARC: deliver project " + task["id"],
                    "tree": tree["sha"],
                    "parents": [parent],
                },
            )
            sha = created["sha"]
            if exists:
                await request(
                    "PATCH",
                    base + "/git/refs/heads/" + branch,
                    {"sha": sha, "force": False},
                )
            else:
                await request(
                    "POST",
                    base + "/git/refs",
                    {"ref": "refs/heads/" + branch, "sha": sha},
                )
            actual = await request("GET", base + "/git/ref/heads/" + branch)
            if actual["object"]["sha"] != sha:
                raise ValueError("GitHub did not confirm the expected commit SHA")
            LOG.info(
                "ARC execution stage=published task=%s repository=%s sha=%s",
                task["id"],
                repository,
                sha,
            )
            return {
                "sha": sha,
                "repository": repository,
                "branch": branch,
                "url": f"https://github.com/{repository}/tree/{branch}/{prefix.rstrip('/')}",
                "commit_url": f"https://github.com/{repository}/commit/{sha}",
            }
        finally:
            if token:
                try:
                    await client.delete(
                        "https://api.github.com/installation/token",
                        headers=headers,
                        timeout=3,
                    )
                except httpx.HTTPError:
                    LOG.warning(
                        "ARC GitHub short-lived token revocation could not connect"
                    )
