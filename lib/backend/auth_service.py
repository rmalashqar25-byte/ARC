"""Database-free session access. This is not a user-account system."""

import hashlib
import os
import secrets
import uuid

from fastapi import HTTPException


def auth_configuration() -> dict[str, bool]:
    key = os.getenv("ARC_BACKEND_API_KEY", "").strip()
    production = os.getenv(
        "ARC_ENVIRONMENT", "development"
    ).lower() == "production" or bool(os.getenv("CONTAINER_APP_NAME"))
    valid_key = len(key) >= 32 and not key.startswith("replace_")
    return {"session_access": valid_key or (not key and not production)}


def resolve_session_actor(session: str | None, api_key: str | None) -> str:
    expected = os.getenv("ARC_BACKEND_API_KEY", "").strip()
    if not auth_configuration()["session_access"]:
        raise HTTPException(503, "Invalid backend access-key configuration")
    if expected and (
        not api_key
        or not secrets.compare_digest(api_key.encode("utf-8"), expected.encode("utf-8"))
    ):
        raise HTTPException(401, "A valid X-Arc-API-Key is required by this server")
    try:
        token = uuid.UUID(session or "")
        if token.version != 4 or str(token) != (session or "").lower():
            raise ValueError()
    except ValueError:
        raise HTTPException(401, "Send a random UUID-v4 in X-Arc-Session") from None
    return "guest:" + hashlib.sha256(str(token).encode()).hexdigest()
