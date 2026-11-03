"""Verify personal API routing with a real zero-price model in a disposable workspace.

Reads the local OpenRouter key without printing it. Never modifies live company
settings, invokes a paid model, or sends existing chats or project files.
"""

import asyncio
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib/backend"))


def main():
    import httpx
    from dotenv import load_dotenv
    from fastapi.testclient import TestClient

    os.environ.pop("PYTHON_DOTENV_DISABLED", None)
    load_dotenv(ROOT / ".env", override=True)
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("No OpenRouter test key is configured locally")
    listed = httpx.get("https://openrouter.ai/api/v1/models", timeout=20).json()["data"]
    model = "nvidia/nemotron-3.5-lightning:free"
    entry = next((m for m in listed if m["id"] == model), None)
    if not entry or "tools" not in entry.get("supported_parameters", []):
        raise RuntimeError("The exact free test model is unavailable")
    pricing = entry.get("pricing", {})
    if not pricing or any(float(v or 0) != 0 for v in pricing.values()):
        raise RuntimeError("Free pricing could not be confirmed; no generation sent")

    from agent_store import get_agent_store
    from app import app
    from company import model_catalog

    model_catalog._catalog = model_catalog.normalize_models(listed)
    from auth_service import resolve_session_actor
    from company.work_runtime import CompanyWorker
    from company.work_store import WorkStore
    from developer_connections import ModelTransport

    session = str(uuid.uuid4())
    project = "api-check-" + uuid.uuid4().hex[:12]
    headers = {"X-Arc-Session": session}
    original = ModelTransport.handle_request
    calls = []
    checks = {}

    def guarded(transport, request):
        if request.url.host != "openrouter.ai" or request.url.path not in {
            "/api/v1/models",
            "/api/v1/key",
            "/api/v1/chat/completions",
        }:
            raise RuntimeError("Unexpected destination blocked")
        if request.url.path.endswith("/chat/completions"):
            body = json.loads(request.content)
            if body.get("model") != model or body.get("models") or len(calls) >= 6:
                raise RuntimeError("Only the exact free test model is allowed")
            response = original(transport, request)
            response.read()
            data = response.json()
            cost = data.get("usage", {}).get("cost")
            calls.append(
                {
                    "status": response.status_code,
                    "cost": cost,
                    "model": data.get("model"),
                    "finish_reason": data.get("choices", [{}])[0].get("finish_reason"),
                    "reply_length": len(
                        data.get("choices", [{}])[0].get("message", {}).get("content")
                        or ""
                    ),
                    "completion_tokens": data.get("usage", {}).get("completion_tokens"),
                }
            )
            if cost is not None and float(cost) != 0:
                raise RuntimeError("Nonzero cost reported; stopped")
            return response
        return original(transport, request)

    def succeeded(response):
        if response.status_code != 200:
            print(json.dumps({"completed_checks": checks, "provider_calls": calls}))
            raise RuntimeError(
                "Connection verification request failed (HTTP %s)"
                % response.status_code
            )
        return response.json()

    with (
        tempfile.TemporaryDirectory(prefix="arc-api-check-") as directory,
        patch.dict(
            os.environ,
            {
                "ARC_PROVIDER_VAULT": str(Path(directory) / "vault"),
                "ARC_AGENT_WORKSPACE_ROOT": str(Path(directory) / "project"),
                "ARC_COMPANY_WORKER_ENABLED": "0",
                "ARC_BACKEND_API_KEY": "",
                "ARC_ENVIRONMENT": "development",
                "CONTAINER_APP_NAME": "",
                "ARC_CEO_MAX_OUTPUT_TOKENS": "1024",
                "ARC_AGENT_MAX_OUTPUT_TOKENS": "1024",
            },
        ),
        patch.object(ModelTransport, "handle_request", guarded),
    ):
        actor = resolve_session_actor(session, None)
        (Path(directory) / "project").mkdir()
        store = get_agent_store()
        db = WorkStore(Path(directory) / "work.sqlite3")
        store.bind_work_store(db)
        with TestClient(app) as client:
            invalid = client.post(
                "/developer/models",
                headers=headers,
                json={"provider": "openrouter", "api_key": "invalid-synthetic-key"},
            )
            checks["invalid_key_rejected"] = invalid.status_code == 401
            if not checks["invalid_key_rejected"]:
                raise RuntimeError("Invalid API key was accepted")
            models = succeeded(
                client.post(
                    "/developer/models",
                    headers=headers,
                    json={"provider": "openrouter", "api_key": key},
                )
            )
            checks["authenticated_models_loaded"] = any(
                m["id"] == model for m in models["models"]
            )
            saved = succeeded(
                client.put(
                    "/developer/connection",
                    headers=headers,
                    json={
                        "provider": "openrouter",
                        "api_key": key,
                        "model": model,
                        "confirm_usage": True,
                        "supports_tools": True,
                    },
                )
            )
            checks["saved_without_returning_key"] = "api_key" not in saved["connection"]
            reread = succeeded(client.get("/developer/connection", headers=headers))
            checks["saved_model_restored"] = reread["connection"]["model"] == model
            answer = succeeded(
                client.post(
                    "/company/ceo/run",
                    headers=headers,
                    json={
                        "session_id": project,
                        "prompt": "Hi. This is only a connection check. Reply with a brief greeting. Do not hire anyone or delegate work.",
                    },
                )
            )
            checks["real_ceo_reply"] = (
                bool(answer.get("message")) and answer.get("model") == model
            )
            succeeded(
                client.put(
                    "/company/sessions/" + project + "/team",
                    headers=headers,
                    json={
                        "mode": "manual",
                        "members": [{"agent_id": model, "role_id": "cto"}],
                    },
                )
            )
            succeeded(
                client.put(
                    "/company/sessions/" + project + "/work",
                    headers=headers,
                    json={
                        "enabled": True,
                        "model": model,
                        "confirm_local_autonomy": True,
                    },
                )
            )
            created = client.post(
                "/company/sessions/" + project + "/work/tasks",
                headers=headers,
                json={
                    "title": "Verify actual tool execution",
                    "description": "For this connection check, personally call the calculator tool to calculate 23 * 19. Report its numeric result. Do not delegate, hire, edit files, or call other tools.",
                    "assignee": "cto",
                    "manager": "ceo",
                },
            )
            if created.status_code != 201:
                raise RuntimeError("The test task could not be queued")
            task = db.claim()
            if not task:
                raise RuntimeError("The queued verification task was not claimed")
            asyncio.run(CompanyWorker(db).process(task))
            finished = db.get(actor, project, task["id"])
            checks["background_agent_completed"] = finished["status"] == "completed"
            checks["actual_calculator_tool_ran"] = any(
                e.get("event") == "tool_completed"
                and e.get("tool") == "calculator"
                and "437" in json.dumps(e.get("details", {}))
                for e in store.audit
            )
            checks["no_tool_approval_prompts"] = not store.pending
            other = client.get(
                "/developer/connection", headers={"X-Arc-Session": str(uuid.uuid4())}
            )
            checks["another_workspace_isolated"] = other.json()["connection"] == {}
            checks["all_calls_free"] = bool(calls) and all(
                c["status"] == 200 and c["cost"] == 0 for c in calls
            )
    report = {
        "status": "passed" if all(checks.values()) else "failed",
        "model": model,
        "checks": checks,
        "model_calls": calls,
    }
    path = ROOT / ".arc/security/developer-api-verification.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not all(checks.values()):
        raise RuntimeError(
            "A connection check failed; see the private verification report"
        )


if __name__ == "__main__":
    main()
