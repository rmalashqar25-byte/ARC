import asyncio
import logging
import os
import re
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from threading import Lock

import httpx
from agent_store import StateCapacityError, get_agent_store
from agent_tools import public_tool_catalog
from auth_service import auth_configuration, resolve_session_actor
from company.common import ALL_AGENT_TOOLS
from company.organization import public_agent_catalog
from company.provider_config import ceo_configuration, configured_secret
from company.work_api import build_work_router
from company_api import build_company_router
from developer_api import build_developer_router
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from github import (
    consume_github_state,
    create_github_authorization,
    exchange_github_code,
    get_github_user,
    get_user_installations,
    github_configuration,
    list_github_connections,
    save_github_connections,
    verify_github_webhook,
)
from pydantic import BaseModel, Field
from security_boundary import SecurityBoundaryMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from terminal_connection import (
    pair_terminal,
    terminal_is_connected,
    terminal_pairing_available,
    terminal_service_ready,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def company_lifespan(app):
    if os.getenv("ARC_COMPANY_WORKER_ENABLED", "").lower() not in {"1", "true"}:
        yield
        return
    from pathlib import Path

    from company.work_runtime import CompanyWorker
    from company.work_store import WorkStore

    path = os.getenv("ARC_COMPANY_DB", "").strip() or str(
        Path.cwd() / ".arc/company.sqlite3"
    )
    store = get_agent_store()
    store.bind_work_store(WorkStore(path))
    worker = CompanyWorker(store.work_store)
    task = asyncio.create_task(worker.run())
    app.state.company_worker = worker
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


app = FastAPI(
    title="ARC Company Backend",
    version="1.0.0",
    description="ARC company orchestration and private work queues.",
    lifespan=company_lifespan,
)
_auth_attempts: dict[str, deque[float]] = defaultdict(deque)
_auth_rate_lock = Lock()
_agent_runs: dict[str, deque[float]] = defaultdict(deque)
_agent_run_rate_lock = Lock()


def _comma_separated_setting(name: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


allowed_origins = _comma_separated_setting("ARC_ALLOWED_ORIGINS")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=None
    if allowed_origins
    else r"https?://(?:localhost|127\.0\.0\.1)(?::\d+)?",
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "X-Arc-API-Key",
        "X-Arc-Session",
        "X-Arc-Worker",
    ],
)

trusted_hosts = _comma_separated_setting("ARC_TRUSTED_HOSTS")
if trusted_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts)


app.add_middleware(SecurityBoundaryMiddleware)


@app.exception_handler(RequestValidationError)
async def validation_error(request, error):
    # Never echo supplied input (which may contain secrets) in error responses.
    return JSONResponse(
        {
            "detail": [
                {"type": item["type"], "loc": item["loc"], "msg": item["msg"]}
                for item in error.errors()
            ]
        },
        status_code=422,
    )


@app.exception_handler(StateCapacityError)
async def state_capacity_error(request, error):
    return JSONResponse(
        {"detail": str(error)}, status_code=503, headers={"Retry-After": "60"}
    )


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", "")
    if not re.fullmatch(r"[A-Za-z0-9._-]{8,128}", request_id):
        request_id = secrets.token_hex(16)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if not request.url.path.startswith(("/docs", "/redoc")):
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        )
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    if request.url.path.startswith(("/company", "/github", "/developer", "/plugins")):
        response.headers["Cache-Control"] = "no-store"
    return response


def _enforce_auth_rate_limit(credential_fingerprint: str) -> None:
    try:
        limit = min(
            max(int(os.getenv("ARC_AUTH_RATE_LIMIT_PER_MINUTE", "600")), 60), 5_000
        )
    except ValueError:
        limit = 600
    now = time.monotonic()
    with _auth_rate_lock:
        attempts = _auth_attempts[credential_fingerprint]
        while attempts and attempts[0] <= now - 60:
            attempts.popleft()
        if len(attempts) >= limit:
            raise HTTPException(
                status_code=429,
                detail="Authentication request rate limit reached.",
                headers={"Retry-After": "60"},
            )
        attempts.append(now)
        if len(_auth_attempts) > 5_000:
            stale = [
                key
                for key, values in _auth_attempts.items()
                if not values or values[-1] <= now - 60
            ]
            for key in stale:
                _auth_attempts.pop(key, None)
            while len(_auth_attempts) > 5_000:
                _auth_attempts.pop(next(iter(_auth_attempts)), None)


def _enforce_agent_run_rate(actor_id: str) -> None:
    try:
        limit = min(max(int(os.getenv("ARC_AGENT_RUNS_PER_MINUTE", "30")), 1), 120)
    except ValueError:
        limit = 30
    now = time.monotonic()
    with _agent_run_rate_lock:
        runs = _agent_runs[actor_id]
        while runs and runs[0] <= now - 60:
            runs.popleft()
        if len(runs) >= limit:
            raise HTTPException(
                status_code=429,
                detail="Agent request rate limit reached.",
                headers={"Retry-After": "60"},
            )
        runs.append(now)
        for key in list(_agent_runs):
            if _agent_runs[key][-1] <= now - 60:
                del _agent_runs[key]
        while len(_agent_runs) > 5000:
            del _agent_runs[next(iter(_agent_runs))]


async def require_agent_access(
    request: Request,
    session: str | None = Header(default=None, alias="X-Arc-Session"),
    api_key: str | None = Header(default=None, alias="X-Arc-API-Key"),
):
    peer = request.client.host if request.client else "unknown"
    if not os.getenv("ARC_BACKEND_API_KEY", "").strip() and peer not in {
        "127.0.0.1",
        "::1",
        "testclient",
    }:
        raise HTTPException(
            503, "Remote access requires a trusted authenticated gateway"
        )
    actor = resolve_session_actor(session, api_key)
    _enforce_auth_rate_limit(actor)
    from developer_connections import DEVELOPER_ACTOR

    token = DEVELOPER_ACTOR.set(actor)
    try:
        yield actor
    finally:
        DEVELOPER_ACTOR.reset(token)


app.include_router(build_developer_router(require_agent_access))

app.include_router(build_company_router(require_agent_access, _enforce_agent_run_rate))

app.include_router(build_work_router(require_agent_access))


@app.get("/")
def read_root():
    return {
        "message": "Welcome to the ARC Company server.",
        "products": ["ARC Company"],
        "company_entry_point": "/company/ceo/run",
        "company_catalog": "/company/catalog",
    }


@app.get("/health/live")
def health_live():
    return {"status": "ok", "service": "arc-backend"}


@app.get("/health/ready")
def health_ready(response: Response):
    try:
        ceo_ready = ceo_configuration()["configured"]
    except RuntimeError:
        ceo_ready = False
    checks = {
        "memory_state": False,
        "openrouter": bool(configured_secret("OPENROUTER_API_KEY")),
        "ceo_provider": ceo_ready,
        "authentication": any(auth_configuration().values()),
    }
    try:
        checks["memory_state"] = get_agent_store().ping()
    except Exception:
        logger.exception("Backend readiness storage check failed")
    ready = all(checks.values())
    if not ready:
        response.status_code = 503
    return {
        "status": "ready" if ready else "not_ready",
        "checks": checks,
        "optional": {"github": github_configuration()},
    }


@app.get("/plugins/catalog")
def plugins_catalog(actor_id: str = Depends(require_agent_access)):
    """Return truthful user-install and readiness state for every agent tool."""
    tools = public_tool_catalog(ALL_AGENT_TOOLS)
    github_status = github_configuration()
    github_connections = list_github_connections(actor_id)
    plugins = []
    for tool in tools:
        tool_name = str(tool["name"])
        plugin = {
            **tool,
            "id": tool_name,
            "display_name": tool_name.replace("_", " ").title(),
            "install_kind": "built_in",
            "installed": True,
            "ready": True,
        }
        if (
            tool_name == "terminal_run"
            and os.getenv("ARC_TERMINAL_GRANTS_FILE", "").strip()
        ):
            connected = terminal_is_connected(actor_id)
            service_ready = terminal_service_ready()
            plugin.update(
                {
                    "install_kind": "local_terminal",
                    "description": "Run approved Git, search, and Python project checks locally. No cloud account is needed. Changes stay in a temporary workspace.",
                    "installed": connected,
                    "ready": connected and service_ready,
                    "available": service_ready
                    and (connected or terminal_pairing_available()),
                    "configuration": [],
                    "connection_state": "ready"
                    if connected and service_ready
                    else "offline"
                    if not service_ready
                    else "pairing_required",
                    "connection_hint": ""
                    if connected and service_ready
                    else "Start the local terminal on this computer, then refresh."
                    if not service_ready
                    else "Connect this temporary workspace with a local connection code.",
                }
            )
        elif tool_name == "git_publish":
            plugin.update(
                {
                    "id": "github",
                    "display_name": "GitHub",
                    "install_kind": "github_app",
                    "installed": bool(github_connections),
                    "ready": bool(github_connections) and github_status["app_worker"],
                    "available": github_status["oauth"],
                    "connect_endpoint": "/github/connect",
                    "connections_endpoint": "/github/connections",
                    "disconnect_endpoint": "/github/connections/{installation_id}",
                    "connections": github_connections,
                    "server_configuration": github_status,
                }
            )
        elif "configured" in tool:
            configured = bool(tool["configured"])
            plugin.update(
                {
                    "install_kind": "managed_connector",
                    "installed": configured,
                    "ready": configured,
                    "available": configured,
                    "action": "administrator_configuration_required"
                    if not configured
                    else "ready",
                }
            )
        plugins.append(plugin)
    return {
        "tools": tools,
        "plugins": plugins,
        "used_by": [str(agent["id"]) for agent in public_agent_catalog()],
        "permission_modes": ["allow", "ask", "deny"],
    }


@app.post("/plugins/terminal/auto-connect")
def auto_terminal(request: Request, actor_id: str = Depends(require_agent_access)):
    from urllib.parse import urlsplit

    from terminal_connection import auto_connect_terminal

    origin = urlsplit(request.headers.get("origin", ""))
    if not request.client or request.client.host not in {
        "127.0.0.1",
        "::1",
        "testclient",
    }:
        raise HTTPException(403, "Automatic terminal connection is local only")
    if (
        origin.hostname not in {"127.0.0.1", "localhost", "::1"}
        or origin.scheme != "http"
    ):
        raise HTTPException(403, "Open ARC on this computer to connect the terminal")
    if not auto_connect_terminal(actor_id):
        raise HTTPException(
            409, "This terminal is unavailable or belongs to another workspace"
        )
    return {"connected": True, "id": "terminal_run"}


class TerminalConnectionRequest(BaseModel):
    code: str = Field(min_length=32, max_length=100)


@app.post("/plugins/terminal/connect")
def connect_terminal(
    payload: TerminalConnectionRequest, actor_id: str = Depends(require_agent_access)
):
    _enforce_agent_run_rate(actor_id)
    if not terminal_service_ready():
        raise HTTPException(503, "The local terminal is not ready")
    try:
        pair_terminal(actor_id, payload.code)
    except (ValueError, OSError):
        raise HTTPException(400, "The connection code is invalid or expired") from None
    return {"connected": True, "id": "terminal_run"}


@app.get("/github/connect")
def github_connect(actor_id: str = Depends(require_agent_access)):
    try:
        return create_github_authorization(actor_id)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/github/connections")
def github_connections(actor_id: str = Depends(require_agent_access)):
    return {"connections": list_github_connections(actor_id)}


@app.delete("/github/connections/{installation_id}")
def disconnect_github(
    installation_id: int, actor_id: str = Depends(require_agent_access)
):
    removed = get_agent_store().delete_github_connection(actor_id, installation_id)
    if not removed:
        raise HTTPException(status_code=404, detail="GitHub connection was not found")
    return {
        "disconnected": True,
        "installation_id": installation_id,
        "message": "Arc removed its local connection metadata; revoke the GitHub App on GitHub if needed.",
    }


@app.post("/github/webhook")
async def github_webhook(
    request: Request,
    signature: str | None = Header(default=None, alias="X-Hub-Signature-256"),
    event: str | None = Header(default=None, alias="X-GitHub-Event"),
    delivery: str | None = Header(default=None, alias="X-GitHub-Delivery"),
):
    payload = await request.body()
    if len(payload) > 1_000_000:
        raise HTTPException(status_code=413, detail="Webhook payload is too large")
    try:
        valid = verify_github_webhook(payload, signature)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid GitHub webhook signature")
    logger.info("Verified GitHub webhook event=%s delivery=%s", event, delivery)
    return {"accepted": True, "event": event, "delivery": delivery}


@app.get("/github/callback")
async def github_callback(
    code: str = Query(min_length=1, max_length=500),
    state: str = Query(min_length=32, max_length=200),
):
    arc_user_id = consume_github_state(state)

    if arc_user_id is None:
        raise HTTPException(
            status_code=400,
            detail=("Invalid or expired GitHub state"),
        )

    try:
        token_data = await exchange_github_code(code)
    except (httpx.HTTPError, RuntimeError, ValueError) as error:
        logger.exception("GitHub OAuth exchange failed")
        raise HTTPException(
            status_code=502, detail="GitHub authorization failed"
        ) from error

    user_token = token_data.get("access_token")

    if user_token is None:
        raise HTTPException(
            status_code=400,
            detail="GitHub authorization failed",
        )

    try:
        github_user = await get_github_user(user_token)
        installations = await get_user_installations(user_token)
    except httpx.HTTPError as error:
        logger.exception("GitHub identity or installation lookup failed")
        raise HTTPException(
            status_code=502, detail="GitHub connection lookup failed"
        ) from error

    if not installations:
        raise HTTPException(
            status_code=400,
            detail=("No Arc GitHub App installation was found."),
        )

    saved = save_github_connections(
        arc_user_id,
        github_user,
        installations,
    )
    if saved == 0:
        raise HTTPException(
            status_code=502, detail="GitHub returned no usable installation"
        )

    return HTMLResponse(
        """
        <html>
            <body>
                <h2>GitHub connected to Arc.</h2>
                <p>You can return to the Arc app.</p>
            </body>
        </html>
        """
    )
