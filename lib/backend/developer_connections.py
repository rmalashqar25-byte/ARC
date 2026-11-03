"""Workspace-owned model connections. Secrets never enter company state or prompts."""

import ipaddress
import json
import os
import socket
import sqlite3
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import Fernet
from openai import OpenAI

DEVELOPER_ACTOR = ContextVar("arc_developer_actor", default=None)
_lock = threading.Lock()
PRESETS = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "ollama": "http://127.0.0.1:11434/v1",
    "custom": "",
}


def vault_root():
    return Path(os.getenv("ARC_PROVIDER_VAULT", ".arc/provider-vault"))


@contextmanager
def _connect():
    root = vault_root()
    root.mkdir(parents=True, exist_ok=True)
    path = root / "connections.sqlite3"
    db = sqlite3.connect(path, timeout=10)
    db.execute(
        "CREATE TABLE IF NOT EXISTS connections (actor TEXT PRIMARY KEY, secret BLOB NOT NULL)"
    )
    path.chmod(0o600)
    try:
        with db:
            yield db
    finally:
        db.close()


def _protect_key(value, *, decrypt):
    if os.name != "nt":
        return value
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(value)
    source = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    crypt = ctypes.windll.crypt32
    operation = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    if not operation(
        ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)
    ):
        raise OSError("The server user cannot unlock the provider vault")
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(result.data, ctypes.c_void_p))


def _cipher(create=False):
    path = vault_root() / "vault.key"
    if create and not path.exists():
        try:
            with path.open("xb") as stream:
                stream.write(_protect_key(Fernet.generate_key(), decrypt=False))
            path.chmod(0o600)
        except FileExistsError:
            pass
    return Fernet(_protect_key(path.read_bytes(), decrypt=True))


def connection(actor=None):
    actor = actor or DEVELOPER_ACTOR.get()
    if not actor or not (vault_root() / "connections.sqlite3").is_file():
        return None
    with _lock, _connect() as db:
        row = db.execute(
            "SELECT secret FROM connections WHERE actor=?", (actor,)
        ).fetchone()
        if row:
            # Fail closed on corruption/lost encryption key; never use ARC's key instead.
            return json.loads(_cipher().decrypt(row[0]))
    return None


def public_connection(value):
    return {k: v for k, v in (value or {}).items() if k != "api_key"}


def local_developer_enabled():
    return (
        os.getenv("ARC_LOCAL_DEVELOPER") == "1"
        and os.getenv("ARC_ENVIRONMENT", "development") != "production"
        and not os.getenv("CONTAINER_APP_NAME")
    )


def validate_endpoint(value):
    if any(ord(c) < 32 for c in value):
        raise ValueError("Enter a valid API base URL")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError("Enter a valid API base URL") from None
    if (
        not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("API URLs cannot contain credentials, queries, or fragments")
    local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if local:
        if (
            not local_developer_enabled()
            or parsed.scheme != "http"
            or port not in {11434, 1234, 8080}
            or parsed.path.rstrip("/") != "/v1"
        ):
            raise ValueError(
                "Local models need ARC's local launcher and a supported /v1 model server"
            )
    elif parsed.scheme != "https" or port not in {None, 443}:
        raise ValueError("Remote model APIs require HTTPS on port 443")
    return value.rstrip("/")


class ModelTransport(httpx.BaseTransport):
    """Pin validated public DNS results for each request; no redirects or proxy env."""

    def __init__(self, base_url):
        self.base = httpx.URL(validate_endpoint(base_url))
        self.inner = httpx.HTTPTransport(retries=0)

    def handle_request(self, request):
        if (request.url.scheme, request.url.host, request.url.port) != (
            self.base.scheme,
            self.base.host,
            self.base.port,
        ):
            raise ValueError("Model requests cannot change destination")
        host = request.url.host
        if host in {"localhost", "127.0.0.1", "::1"}:
            # Validate again so local connections cannot survive disabling local mode.
            validate_endpoint(str(self.base))
            address = "::1" if host == "::1" else "127.0.0.1"
        else:
            addresses = {
                item[4][0]
                for item in socket.getaddrinfo(
                    host, request.url.port or 443, type=socket.SOCK_STREAM
                )
            }
            if not addresses or any(
                not ipaddress.ip_address(a).is_global for a in addresses
            ):
                raise ValueError("Private and reserved model destinations are blocked")
            address = sorted(addresses)[0]
        request.headers["Host"] = request.url.netloc.decode()
        request.extensions["sni_hostname"] = host
        request.url = request.url.copy_with(host=address)
        return self.inner.handle_request(request)

    def close(self):
        self.inner.close()


def model_client(value):
    return OpenAI(
        base_url=value["base_url"],
        api_key=value.get("api_key") or "local-model",
        timeout=90,
        max_retries=0,
        http_client=httpx.Client(
            transport=ModelTransport(value["base_url"]),
            follow_redirects=False,
            trust_env=False,
        ),
    )


def completion_options(value, token_limit):
    """Direct OpenAI uses the current Chat Completions output-limit parameter."""
    options = {
        "max_completion_tokens"
        if value["provider"] == "openai"
        else "max_tokens": token_limit
    }
    if value["provider"] == "ollama":
        options["reasoning_effort"] = "none"
    return options


def discover_models(value):
    """Authenticate OpenRouter separately: its public catalog accepts invalid keys."""
    with model_client(value).with_options(timeout=15) as client:
        if value["provider"] == "openrouter":
            client.get("/key", cast_to=dict[str, object])
        response = client.models.list()
        return [
            {"id": m.id, "name": str(getattr(m, "name", None) or m.id)[:200]}
            for m in response.data[:2000]
            if isinstance(m.id, str) and len(m.id) <= 200
        ]


def validated_settings(actor, payload, *, discovery=False):
    value = dict(payload)
    provider = value["provider"]
    endpoint = (
        value.get("base_url", "").strip() if provider == "custom" else PRESETS[provider]
    )
    value["base_url"] = validate_endpoint(endpoint)
    value["model"] = value["model"].strip() or ("__discover__" if discovery else "")
    if not value["model"] or any(ord(c) < 32 for c in value["model"]):
        raise ValueError("Enter the exact model ID")
    previous = connection(actor)
    key = value.get("api_key", "").strip()
    if (
        not key
        and previous
        and previous["base_url"] == value["base_url"]
        and previous["provider"] == provider
    ):
        key = previous.get("api_key", "")
    if any(ord(c) < 32 for c in key):
        raise ValueError("Enter a valid API key")
    local = urlsplit(value["base_url"]).scheme == "http"
    if not local and not key:
        raise ValueError("An API key is required for this provider")
    if not local and not discovery and not value.get("confirm_usage"):
        raise ValueError("Confirm that your provider's usage charges apply")
    value["api_key"] = "" if local else key
    value["local"] = local
    return value


def save_connection(actor, value):
    with _lock, _connect() as db:
        secret = _cipher(create=True).encrypt(json.dumps(value).encode())
        db.execute("INSERT OR REPLACE INTO connections VALUES (?, ?)", (actor, secret))
    return public_connection(value)


def delete_connection(actor):
    if not (vault_root() / "connections.sqlite3").is_file():
        return
    with _lock, _connect() as db:
        db.execute("DELETE FROM connections WHERE actor=?", (actor,))


def model_entry(value):
    model = value["model"]
    # Tool capability is a developer declaration, never a fabricated benchmark.
    tools = value.get("supports_tools", True)
    return {
        "id": model,
        "model_id": model,
        "name": value.get("model_name") or model,
        "provider": value["provider"],
        "summary": "Your connected model. "
        + (
            "Tool calling enabled by you."
            if tools
            else "Chat and planning only; tool calling disabled."
        ),
        "categories": [
            "it",
            "research",
            "operations",
            "marketing",
            "finance",
            "legal",
            "design",
        ],
        "configured": tools,
        "agent_compatible": tools,
        "supports_tools": tools,
        "supports_reasoning": False,
        "created": 0,
        "context_length": 0,
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "input_price_per_million": 0 if value["local"] else None,
        "output_price_per_million": 0 if value["local"] else None,
        "developer_connection": True,
        "role_id": "cto",
        "role": "Choose a company role",
        "price": 0,
        "considerations": "Uses your connection for the CEO and all company roles. Model quality and tool support depend on your chosen model. Check usage prices with your provider.",
    }
