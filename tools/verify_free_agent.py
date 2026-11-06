"""Run a real, free-model company task against disposable synthetic files.

Requires an already configured OpenRouter key and an already paired local
terminal. Never changes the running application's model or approval settings.
"""

import argparse
import asyncio
import hashlib
import json
import os
import sys
import tempfile
import threading
import uuid
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib/backend"))


def main():
    import httpx
    from dotenv import load_dotenv
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from openai import OpenAI

    # Match the local launcher instead of inheriting a stale shell credential.
    os.environ.pop("PYTHON_DOTENV_DISABLED", None)
    load_dotenv(ROOT / ".env", override=True)
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model", required=True, help="An exact :free model with tool support"
    )
    parser.add_argument(
        "--background",
        action="store_true",
        help="Verify the durable company worker and default approvals",
    )
    parser.add_argument(
        "--gateway-config",
        type=Path,
        default=ROOT / ".arc/terminal-runtime/gateway.json",
    )
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--max-model-requests", type=int, default=16, choices=range(1, 17)
    )
    args = parser.parse_args()
    model = args.model
    if not model.endswith(":free"):
        parser.error("Only explicit :free models are permitted.")
    response = httpx.get("https://openrouter.ai/api/v1/models", timeout=25)
    response.raise_for_status()
    models = response.json()["data"]
    selected = next((item for item in models if item["id"] == model), None)
    if not selected or "tools" not in selected.get("supported_parameters", []):
        parser.error("This free model is not currently listed with tool support.")
    pricing = selected.get("pricing", {})
    if any(float(pricing.get(name, -1)) != 0 for name in ("prompt", "completion")):
        parser.error("The current catalog does not confirm zero token prices.")
    if any(float(value or 0) != 0 for value in pricing.values()):
        parser.error("This model lists additional nonzero charges.")
    if selected.get("reasoning", {}).get("mandatory") is True:
        parser.error(
            "Choose a model with optional reasoning for this bounded live check."
        )
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        parser.error(
            "Configure OpenRouter locally first; do not put credentials in arguments."
        )

    settings = json.loads(args.gateway_config.read_text())
    grants = json.loads(Path(settings["grants_file"]).read_text())
    actors = grants.get("actors", [])
    if not actors:
        parser.error("Pair the local terminal before running this verification.")
    actor = actors[0]
    session = "free-check-" + uuid.uuid4().hex[:12]
    os.environ.update(
        {
            "ARC_CEO_PROVIDER": "openrouter",
            "ARC_CEO_MODEL": model,
            "ARC_CEO_MAX_OUTPUT_TOKENS": "2048",
            "ARC_AGENT_MAX_OUTPUT_TOKENS": "3072",
            "ARC_CEO_REASONING": "off",
            "ARC_AGENT_REASONING": "off",
            "ARC_TERMINAL_RUNNER_URL": "http://127.0.0.1:8768/run",
            "ARC_TERMINAL_RUNNER_TOKEN": settings["token"],
            "ARC_TERMINAL_GRANTS_FILE": settings["grants_file"],
        }
    )

    from agent_store import get_agent_store
    from agent_tools import TOOL_REGISTRY, ToolContext, _terminal_run, _workspace_root
    from company import model_catalog
    from company_api import build_company_router

    model_catalog._catalog = model_catalog.normalize_models(models)
    store = get_agent_store()
    store.set_approval_mode(actor, "ask" if args.background else "allow")
    allowed = {
        "workspace_read",
        "workspace_search",
        "workspace_update",
        "terminal_run",
        "calculator",
        "delegate_agent",
    }
    for role in ("ceo", "cto", "app_developer"):
        for name in set(TOOL_REGISTRY) - allowed:
            store.set_permission(
                actor, role, session, name, "deny", {}, expires_at=10**12, max_uses=1
            )

    calls = []
    gate = threading.Lock()

    def inspect_request(request):
        if (
            request.url.host != "openrouter.ai"
            or request.url.path != "/api/v1/chat/completions"
        ):
            raise RuntimeError("Unexpected provider destination blocked")
        payload = json.loads(request.content)
        if payload.get("model") != model or payload.get("models"):
            raise RuntimeError("Unapproved model or fallback blocked")
        with gate:
            if len(calls) >= args.max_model_requests:
                raise RuntimeError("Live verification request budget exhausted")
            calls.append({"requested_model": model})
            return len(calls) - 1

    def inspect_response(index, response):
        calls[index]["http_status"] = response.status_code
        if response.status_code == 200:
            data = response.json()
            cost = data.get("usage", {}).get("cost")
            calls[index].update(returned_model=data.get("model"), cost=cost)
            choice = data.get("choices", [{}])[0]
            message = choice.get("message", {})
            calls[index].update(
                finish_reason=choice.get("finish_reason"),
                content_length=len(message.get("content") or ""),
                completion_tokens=data.get("usage", {}).get("completion_tokens"),
            )
            if cost is not None and float(cost) != 0:
                raise RuntimeError(
                    "Provider reported a nonzero cost; further work stopped"
                )

    class SyncGuard(httpx.BaseTransport):
        def __init__(self):
            self.inner = httpx.HTTPTransport()

        def handle_request(self, request):
            index = inspect_request(request)
            response = self.inner.handle_request(request)
            response.read()
            inspect_response(index, response)
            return response

        def close(self):
            self.inner.close()

    class AsyncGuard(httpx.AsyncBaseTransport):
        def __init__(self):
            self.inner = httpx.AsyncHTTPTransport()

        async def handle_async_request(self, request):
            if (
                request.method == "GET"
                and request.url.host == "openrouter.ai"
                and request.url.path == "/api/v1/models"
            ):
                return await self.inner.handle_async_request(request)
            if (
                request.url.host == "127.0.0.1"
                and request.url.port == 8768
                and request.url.path in {"/run", "/health"}
            ):
                return await self.inner.handle_async_request(request)
            index = inspect_request(request)
            response = await self.inner.handle_async_request(request)
            await response.aread()
            inspect_response(index, response)
            return response

        async def aclose(self):
            await self.inner.aclose()

    real_async_client = httpx.AsyncClient

    def ceo_client(**kwargs):
        return real_async_client(**kwargs, transport=AsyncGuard())

    report = {
        "model": model,
        "synthetic_files_only": True,
        "provider_calls": calls,
        "checks": {},
    }
    output = args.report or ROOT / (
        ".arc/security/company-worker-verification.json"
        if args.background
        else ".arc/security/free-agent-verification.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with (
            tempfile.TemporaryDirectory(prefix="arc-free-check-") as temporary,
            ExitStack() as stack,
        ):
            os.environ["ARC_AGENT_WORKSPACE_ROOT"] = temporary
            workspace = _workspace_root(actor, session)
            (workspace / "shipping.py").write_text(
                "def total_after_discount(subtotal, discount):\n    return subtotal + discount\n"
            )
            (workspace / "test_shipping.py").write_text(
                "from shipping import total_after_discount\n\ndef test_discount():\n    assert total_after_discount(100, 10) == 90\n    assert total_after_discount(25, 5) == 20\n"
            )
            original = hashlib.sha256(
                (workspace / "shipping.py").read_bytes()
            ).hexdigest()
            test_original = (workspace / "test_shipping.py").read_bytes()
            context = ToolContext("cto", session, actor, workspace)
            baseline = asyncio.run(
                _terminal_run({"argv": ["python", "-m", "pytest", "-q"]}, context)
            )
            baseline_command = baseline.get("result", {})
            assert baseline_command.get("exit_code") == 1, (
                "The seeded failing test must really fail first"
            )
            report["checks"]["baseline_failure"] = True
            print("Baseline confirmed: the synthetic discount test fails.", flush=True)
            app = FastAPI()
            app.include_router(build_company_router(lambda: actor))
            api = stack.enter_context(TestClient(app))
            client = stack.enter_context(
                OpenAI(
                    base_url="https://openrouter.ai/api/v1",
                    api_key=key,
                    timeout=90,
                    max_retries=0,
                    http_client=httpx.Client(transport=SyncGuard()),
                )
            )
            stack.enter_context(
                patch("company.runtime._openrouter_client", return_value=client)
            )
            stack.enter_context(
                patch("company.ceo.httpx.AsyncClient", side_effect=ceo_client)
            )
            hired = api.put(
                f"/company/sessions/{session}/team",
                json={
                    "mode": "manual",
                    "members": [
                        {"agent_id": model, "role_id": role}
                        for role in ("cto", "app_developer")
                    ],
                },
            )
            assert hired.status_code == 200, "Free model hiring failed"
            report["checks"]["hired_exact_free_model"] = True
            task = (
                "This is a disposable example shop project. I already chose the team in manual mode. "
                "Delegate this bounded implementation task to our CTO now; do not ask me for approval. "
                "The CTO may use the hired app_developer. Inspect shipping.py and test_shipping.py using workspace_read. "
                "The total_after_discount helper incorrectly adds the discount. Fix the function using workspace_update, "
                'then call terminal_run with argv ["python", "-m", "pytest", "-q"]. Do not modify the tests. '
                "Also create README.md with local test instructions using workspace_update, create_if_missing=true, old_text=an empty string and new_text=the document. "
                "Use relative project paths, never /workspace paths. Our local tools are approved for this synthetic check. Use no external services. "
                "Report success only after the actual test command succeeds. Return the test result and a short explanation."
            )
            if args.background:
                from company.work_runtime import CompanyWorker
                from company.work_store import WorkStore

                database = WorkStore(Path(temporary) / "company.sqlite3")
                store.bind_work_store(database)
                database.configure(actor, session, False, model)
                greeting = api.post(
                    "/company/ceo/run",
                    json={
                        "session_id": session,
                        "prompt": "Hello. Greet me briefly; there is no task to delegate.",
                    },
                )
                report["checks"]["paused_chat_uses_selected_model"] = (
                    greeting.status_code == 200
                    and not database.company(actor, session)["enabled"]
                    and not database.list(actor, session)
                )
                database.configure(actor, session, True, model)
                queued = database.create(
                    actor,
                    session,
                    title="Fix the discount bug",
                    description=task,
                    assignee="ceo",
                    requires_check=True,
                )

                async def background_check():
                    worker = CompanyWorker(database)
                    runner = asyncio.create_task(worker.run())
                    try:
                        for _ in range(240):
                            state = database.get(actor, session, queued["id"])
                            if state["status"] in {"completed", "blocked"}:
                                break
                            await asyncio.sleep(1)
                        else:
                            raise RuntimeError(
                                "Company worker did not finish within its test deadline"
                            )
                    finally:
                        runner.cancel()
                        await asyncio.gather(runner, return_exceptions=True)
                    count, events = len(calls), len(store.events)
                    await worker.tick()
                    await worker.tick()
                    report["checks"]["quiet_idle"] = (
                        len(calls) == count and len(store.events) == events
                    )
                    return database.get(actor, session, queued["id"])

                state = asyncio.run(background_check())
                report["agent_trace"] = [
                    dict(
                        {
                            k: message[k]
                            for k in ("role", "content", "tool_calls")
                            if k in message
                        },
                        agent=role,
                    )
                    for (owner, role, memory), messages in store.sessions.items()
                    if owner == actor
                    and memory.startswith(session + ":")
                    and isinstance(messages, list)
                    for message in messages
                    if message.get("role") in {"assistant", "tool"}
                ]
                report["checks"]["company_worker_completed"] = (
                    state["status"] == "completed"
                )
                report["checks"]["default_approvals_unchanged"] = (
                    store.get_approval_mode(actor) == "ask"
                )
                restored = WorkStore(database.path)
                report["checks"]["result_survives_restart"] = (
                    restored.get(actor, session, queued["id"])["status"] == "completed"
                )
                report["ceo_message"] = state["result"] or state["feedback"]
                report["checks"]["delegated"] = any(
                    job.get("parent") == queued["id"]
                    for job in database.list(actor, session)
                )
                report["checks"][
                    "no_approval_prompts"
                ] = not store.list_pending_actions(actor)
            else:
                result = api.post(
                    "/company/ceo/run", json={"session_id": session, "prompt": task}
                )
                report["http_status"] = result.status_code
                if result.status_code != 200:
                    raise RuntimeError(f"CEO task returned HTTP {result.status_code}")
                body = result.json()
                report["ceo_message"] = body.get("message")
                report["checks"]["delegated"] = bool(body.get("delegations"))
                report["checks"]["no_approval_prompts"] = not body.get(
                    "pending_approvals"
                )
            audit = store.audit
            completed = [
                e
                for e in audit
                if e.get("actor_id") == actor
                and e.get("session_id") == session
                and e.get("event") == "tool_completed"
            ]
            report["completed_tools"] = [e.get("tool") for e in completed]
            report["checks"]["agent_test_command_passed"] = any(
                e.get("tool") == "terminal_run"
                and e.get("details", {})
                .get("result", {})
                .get("result", {})
                .get("exit_code")
                == 0
                for e in completed
            )
            report["checks"]["agent_used_update_and_terminal"] = {
                "workspace_update",
                "terminal_run",
            }.issubset(report["completed_tools"])
            report["checks"]["file_changed_by_agent"] = (
                hashlib.sha256((workspace / "shipping.py").read_bytes()).hexdigest()
                != original
            )
            report["checks"]["new_project_file_created"] = (
                workspace / "README.md"
            ).is_file() and any(
                e.get("tool") == "workspace_update"
                and e.get("details", {}).get("result", {}).get("status") == "created"
                for e in completed
            )
            report["checks"]["tests_unchanged"] = (
                workspace / "test_shipping.py"
            ).read_bytes() == test_original
            final = asyncio.run(
                _terminal_run({"argv": ["python", "-m", "pytest", "-q"]}, context)
            ).get("result", {})
            report["test_output"] = final.get("output", "")
            report["checks"]["independent_test_pass"] = final.get(
                "exit_code"
            ) == 0 and "1 passed" in final.get("output", "")
            events = api.get(f"/company/sessions/{session}/events").json()["events"]
            report["checks"]["activity_recorded"] = len(events) >= 3
            report["checks"]["other_actor_isolated"] = not store.list_company_events(
                "unrelated-test-actor", session
            )
            assert all(report["checks"].values()), (
                "One or more live workflow checks failed"
            )
            report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["failure_type"] = type(error).__name__
        print(
            "Live workflow verification failed; see the private report for completed checks.",
            flush=True,
        )
    finally:
        report["tool_events"] = [
            {
                "event": e.get("event"),
                "tool": e.get("tool"),
                "details": e.get("details"),
            }
            for e in store.audit
            if e.get("actor_id") == actor and e.get("session_id") == session
        ]
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "checks": report["checks"],
                "provider_requests": len(calls),
            }
        ),
        flush=True,
    )
    return report["status"] != "passed"


if __name__ == "__main__":
    raise SystemExit(main())
