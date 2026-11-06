"""Explicit, one-time pairing of a local workspace to its terminal service."""

import hashlib
import hmac
import json
import os
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx

_lock = threading.Lock()
_health_lock = threading.Lock()
_health_cache = (0, False)


def terminal_service_ready():
    global _health_cache
    with _health_lock:
        if time.monotonic() - _health_cache[0] < 5:
            return _health_cache[1]
        endpoint = os.getenv("ARC_TERMINAL_RUNNER_URL", "").strip()
        token = os.getenv("ARC_TERMINAL_RUNNER_TOKEN", "").strip()
        if not endpoint or not token or not _state_path():
            return False
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            return False
        health_url = urlunsplit((parsed.scheme, parsed.netloc, "/health", "", ""))
        try:
            response = httpx.get(
                health_url,
                headers={"Authorization": "Bearer " + token},
                timeout=10,
                follow_redirects=False,
            )
            ready = response.status_code == 200 and response.json().get("ready") is True
        except (httpx.HTTPError, ValueError):
            ready = False
        _health_cache = (time.monotonic(), ready)
        return ready


def _state_path():
    value = os.getenv("ARC_TERMINAL_GRANTS_FILE", "").strip()
    return Path(value) if value else None


def _state():
    path = _state_path()
    if not path or not path.is_file() or path.stat().st_size > 64_000:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def terminal_is_connected(actor_id):
    return actor_id in _state().get("actors", [])


def terminal_pairing_available():
    state = _state()
    return bool(
        state.get("pairing_hash")
        and not state.get("paired")
        and state.get("expires_at", 0) > time.time()
    )


def pair_terminal(actor_id, code):
    if not re.fullmatch(r"guest:[a-f0-9]{64}", actor_id):
        raise ValueError("A valid workspace session is required")
    with _lock:
        state = _state()
        if actor_id in state.get("actors", []):
            return
        expected = state.get("pairing_hash", "")
        supplied = hashlib.sha256(code.encode()).hexdigest()
        if (
            not expected
            or state.get("paired")
            or state.get("expires_at", 0) <= time.time()
            or not hmac.compare_digest(expected, supplied)
        ):
            raise ValueError("The connection code is invalid or expired")
        state.update(actors=[actor_id], paired=True)
        state.pop("pairing_hash", None)
        path = _state_path()
        if not path:
            raise ValueError("Terminal setup is unavailable")
        temporary = path.with_suffix(".new")
        temporary.write_text(json.dumps(state), encoding="utf-8")
        temporary.chmod(0o640)
        temporary.replace(path)


def auto_connect_terminal(actor_id):
    """Local launcher only; never add a second workspace or grant remote access."""
    from developer_connections import local_developer_enabled

    if terminal_is_connected(actor_id):
        return True
    if not local_developer_enabled() or os.getenv("ARC_TERMINAL_AUTO_CONNECT") != "1":
        return False
    if (
        not re.fullmatch(r"guest:[a-f0-9]{64}", actor_id)
        or not terminal_service_ready()
    ):
        return False
    with _lock:
        state = _state()
        if not state or state.get("actors"):
            return False
        path = _state_path()
        state.update(actors=[actor_id], paired=True)
        state.pop("pairing_hash", None)
        temporary = path.with_suffix(".new")
        temporary.write_text(json.dumps(state), encoding="utf-8")
        temporary.chmod(0o640)
        temporary.replace(path)
        return True


def restore_verified_terminal(actor_id):
    """Restore the same verified GitHub identity, never an anonymous workspace."""
    from agent_store import get_agent_store

    store = get_agent_store()
    current = store.list_github_connections(actor_id)
    with _lock:
        state = _state()
        if actor_id in state.get("actors", []):
            return True
        if not state.get("actors") or len(state["actors"]) >= 16:
            return False
        with store._lock:
            prior = list(store.connections.items())
        same_owner = any(
            old_actor in state["actors"]
            and old.get("github_user_id")
            and old.get("github_user_id") == new.get("github_user_id")
            and installation == new.get("installation_id")
            for (old_actor, installation), old in prior
            for new in current
        )
        if not same_owner:
            return False
        state["actors"].append(actor_id)
        path = _state_path()
        temporary = path.with_suffix(".restore")
        temporary.write_text(json.dumps(state), encoding="utf-8")
        temporary.chmod(0o640)
        temporary.replace(path)
        return True
