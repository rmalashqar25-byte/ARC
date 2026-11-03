"""GitHub OAuth helpers and webhook verification for the Arc backend."""

import hashlib
import hmac
import os
import re
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from agent_store import get_agent_store

GITHUB_API = "https://api.github.com"
GITHUB_OAUTH = "https://github.com/login/oauth"
GITHUB_API_VERSION = "2022-11-28"
OAUTH_STATE_TTL_SECONDS = 10 * 60


def _setting(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


def github_configuration() -> dict[str, bool]:
    return {
        "oauth": bool(
            os.getenv("GITHUB_CLIENT_ID", "").strip()
            and os.getenv("GITHUB_CLIENT_SECRET", "").strip()
            and os.getenv("GITHUB_CALLBACK_URL", "").strip()
            and os.getenv("GITHUB_APP_SLUG", "").strip()
        ),
        "app_worker": bool(
            os.getenv("GITHUB_APP_ID", "").strip()
            and (
                os.getenv("GITHUB_PRIVATE_KEY", "").strip()
                or os.getenv("GITHUB_PRIVATE_KEY_PATH", "").strip()
            )
        ),
        "webhook": bool(os.getenv("GITHUB_WEBHOOK_SECRET", "").strip()),
    }


def save_github_state(state: str, arc_user_id: str) -> None:
    if len(state) < 32:
        raise ValueError("OAuth state is too short")
    get_agent_store().create_github_oauth_state(
        hashlib.sha256(state.encode("utf-8")).hexdigest(),
        arc_user_id,
        time.time() + OAUTH_STATE_TTL_SECONDS,
    )


def consume_github_state(state: str) -> str | None:
    if not state:
        return None
    digest = hashlib.sha256(state.encode("utf-8")).hexdigest()
    return get_agent_store().consume_github_oauth_state(digest)


def create_github_authorization(arc_user_id: str) -> dict[str, Any]:
    for name in (
        "GITHUB_CLIENT_ID",
        "GITHUB_CLIENT_SECRET",
        "GITHUB_CALLBACK_URL",
        "GITHUB_APP_SLUG",
    ):
        _setting(name)
    state = secrets.token_urlsafe(40)
    save_github_state(state, arc_user_id)
    query = urlencode(
        {
            "client_id": _setting("GITHUB_CLIENT_ID"),
            "redirect_uri": _setting("GITHUB_CALLBACK_URL"),
            "state": state,
            "allow_signup": "false",
        }
    )
    return {
        "authorization_url": f"{GITHUB_OAUTH}/authorize?{query}",
        "installation_url": f"https://github.com/apps/{_setting('GITHUB_APP_SLUG')}/installations/new",
        "expires_in_seconds": OAUTH_STATE_TTL_SECONDS,
    }


def _github_headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": "ARC-Agent-Backend",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def exchange_github_code(code: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
        response = await client.post(
            f"{GITHUB_OAUTH}/access_token",
            headers={"Accept": "application/json", "User-Agent": "ARC-Agent-Backend"},
            data={
                "client_id": _setting("GITHUB_CLIENT_ID"),
                "client_secret": _setting("GITHUB_CLIENT_SECRET"),
                "code": code,
                "redirect_uri": _setting("GITHUB_CALLBACK_URL"),
            },
        )
        response.raise_for_status()
        data = response.json()
    if data.get("error"):
        raise ValueError(str(data.get("error_description") or data["error"]))
    return data


async def get_github_user(user_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
        response = await client.get(
            f"{GITHUB_API}/user", headers=_github_headers(user_token)
        )
        response.raise_for_status()
        return response.json()


async def get_user_installations(user_token: str) -> list[dict[str, Any]]:
    installations: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
        page = 1
        while page <= 10:
            response = await client.get(
                f"{GITHUB_API}/user/installations",
                headers=_github_headers(user_token),
                params={"per_page": 100, "page": page},
            )
            response.raise_for_status()
            batch = response.json().get("installations", [])
            installations.extend(item for item in batch if isinstance(item, dict))
            if len(batch) < 100:
                break
            page += 1

    expected_slug = _setting("GITHUB_APP_SLUG").lower()
    return [
        item
        for item in installations
        if str(item.get("app_slug", "")).lower() == expected_slug
    ]


def save_github_connections(
    arc_user_id: str,
    github_user: dict[str, Any],
    installations: list[dict[str, Any]],
) -> int:
    saved = 0
    for installation in installations:
        account = installation.get("account") or {}
        installation_id = installation.get("id")
        if not installation_id or not account.get("login"):
            continue
        get_agent_store().save_github_connection(
            actor_id=arc_user_id,
            installation_id=int(installation_id),
            account_login=str(account["login"]),
            account_type=str(account.get("type", "Unknown")),
            github_user_id=str(github_user.get("id", "")),
            github_user_login=str(github_user.get("login", "")),
        )
        saved += 1
    return saved


def list_github_connections(arc_user_id: str) -> list[dict[str, Any]]:
    return get_agent_store().list_github_connections(arc_user_id)


def verify_github_webhook(payload: bytes, signature: str | None) -> bool:
    secret = _setting("GITHUB_WEBHOOK_SECRET").encode("utf-8")
    if not signature or not re.fullmatch(r"sha256=[0-9a-f]{64}", signature):
        return False
    expected = "sha256=" + hmac.new(secret, payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
