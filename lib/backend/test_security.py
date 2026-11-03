"""Adversarial regressions: synthetic files and mocked providers only."""

import asyncio
import json
import os
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

from agent_store import AgentStore, get_agent_store
from agent_tools import (
    ToolContext,
    _calculate,
    _validate_terminal_argv,
    _workspace_read,
    dispatch_tool,
    make_tool_context,
    resolve_pending_action,
    set_tool_permission,
)
from app import app
from fastapi.testclient import TestClient


class ToolBoundarySecurityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.actor = "security-" + uuid.uuid4().hex
        get_agent_store().set_approval_mode(self.actor, "allow")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.context = ToolContext("it", "project", self.actor, self.root)
        (self.root / "allowed.txt").write_text("before")
        (self.root / "private.txt").write_text("before")

    async def update(self, path="allowed.txt", force=False):
        return await dispatch_tool(
            ("workspace_update",),
            "workspace_update",
            {"path": path, "old_text": "before", "new_text": "after"},
            self.context,
            force_one_time_approval=force,
        )

    async def test_new_project_file_creation_is_bounded_and_never_clobbers(self):
        arguments = {
            "path": "src/demo.py",
            "old_text": "",
            "new_text": "print('demo')",
            "create_if_missing": True,
        }
        result, pending = await dispatch_tool(
            ("workspace_update",), "workspace_update", arguments, self.context
        )
        self.assertIsNone(pending)
        self.assertEqual(result["output"]["status"], "created")
        self.assertEqual((self.root / "src/demo.py").read_text(), "print('demo')")
        arguments["new_text"] = "replacement"
        again, _ = await dispatch_tool(
            ("workspace_update",), "workspace_update", arguments, self.context
        )
        self.assertEqual(again["status"], "failed")
        self.assertEqual((self.root / "src/demo.py").read_text(), "print('demo')")
        for path in (
            "../escape.py",
            ".env",
            "secrets/demo.py",
            "demo.py:stream.py",
            "demo.exe",
        ):
            rejected, _ = await dispatch_tool(
                ("workspace_update",),
                "workspace_update",
                dict(arguments, path=path),
                self.context,
            )
            self.assertEqual(rejected["status"], "failed", path)

    async def test_new_file_creation_obeys_explicit_denies(self):
        set_tool_permission(
            self.actor, "it", "project", "workspace_update", "deny", 10, 1, {}
        )
        result, pending = await dispatch_tool(
            ("workspace_update",),
            "workspace_update",
            {
                "path": "new.py",
                "old_text": "",
                "new_text": "safe",
                "create_if_missing": True,
            },
            self.context,
        )
        self.assertEqual(result["status"], "denied")
        self.assertIsNone(pending)
        self.assertFalse((self.root / "new.py").exists())

    async def test_explicit_deny_overrides_global_allow(self):
        set_tool_permission(
            self.actor, "it", "project", "workspace_update", "deny", 10, 1, {}
        )
        result, pending = await self.update()
        self.assertEqual(result["status"], "denied")
        self.assertIsNone(pending)
        self.assertEqual((self.root / "allowed.txt").read_text(), "before")

    async def test_scoped_allow_does_not_authorize_other_files(self):
        set_tool_permission(
            self.actor,
            "it",
            "project",
            "workspace_update",
            "allow",
            10,
            1,
            {"paths": ["allowed.txt"]},
        )
        result, pending = await self.update("private.txt")
        self.assertEqual(result["status"], "approval_required")
        self.assertEqual((self.root / "private.txt").read_text(), "before")
        self.assertEqual(
            get_agent_store().get_permission(
                self.actor, "it", "project", "workspace_update"
            )["remaining_uses"],
            1,
        )

    async def test_one_use_grant_cannot_fall_back_to_global_allow(self):
        set_tool_permission(
            self.actor,
            "it",
            "project",
            "workspace_update",
            "allow",
            10,
            1,
            {"paths": ["allowed.txt"]},
        )
        first, _ = await self.update()
        self.assertEqual(first["status"], "completed")
        (self.root / "allowed.txt").write_text("before")
        second, _ = await self.update()
        self.assertEqual(second["status"], "approval_required")

    async def test_forced_approval_cannot_be_skipped(self):
        result, pending = await self.update(force=True)
        self.assertEqual(result["status"], "approval_required")
        self.assertIsNotNone(pending)

    async def test_revoking_permission_invalidates_queued_approval(self):
        get_agent_store().set_approval_mode(self.actor, "ask")
        _, pending = await self.update()
        set_tool_permission(
            self.actor, "it", "project", "workspace_update", "deny", 10, 1, {}
        )
        with patch("agent_tools._workspace_root", return_value=self.root):
            result = await resolve_pending_action(
                pending["approval_id"],
                pending["approval_token"],
                "project",
                True,
                self.actor,
            )
        self.assertEqual(result["status"], "denied")
        self.assertEqual((self.root / "allowed.txt").read_text(), "before")

    async def test_terminal_never_starts_a_server_subprocess(self):
        with (
            patch("subprocess.run") as execute,
            patch.dict(
                os.environ,
                {"ARC_TERMINAL_RUNNER_URL": "", "ARC_TERMINAL_RUNNER_TOKEN": ""},
            ),
        ):
            result, _ = await dispatch_tool(
                ("terminal_run",),
                "terminal_run",
                {"argv": ["python", "-m", "pytest"]},
                self.context,
            )
        execute.assert_not_called()
        self.assertNotEqual(result.get("output", {}).get("status"), "completed")

    def test_secret_directories_and_windows_aliases_blocked(self):
        for name in [
            "secrets/settings.json",
            ".aws/config.json",
            ".ssh/config.txt",
            "safe.txt:stream.txt",
            "allowed.txt.",
            "CON.txt",
        ]:
            with self.subTest(name=name):
                target = self.root / name
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text("SYNTHETIC_SECRET")
                except OSError:
                    pass
                with self.assertRaises(ValueError):
                    _workspace_read({"path": name}, self.context)

    def test_oversized_file_rejected_before_read(self):
        (self.root / "large.txt").write_bytes(b"x" * 1_000_001)
        with self.assertRaises(ValueError):
            _workspace_read({"path": "large.txt"}, self.context)

    def test_executable_path_cannot_impersonate_allowlisted_binary(self):
        for argv in [
            ["C:/attacker/git.exe", "status"],
            ["./git", "status"],
            ["rg", "-uuu", "secret", "."],
            ["git", "log", "--output=leak.txt"],
        ]:
            with self.subTest(argv=argv), self.assertRaises(ValueError):
                _validate_terminal_argv(argv)

    def test_workspace_isolated_by_actor_and_project(self):
        with patch.dict(os.environ, {"ARC_AGENT_WORKSPACE_ROOT": str(self.root)}):
            a = make_tool_context("it", "one", actor_id="a").workspace_root
            b = make_tool_context("it", "one", actor_id="b").workspace_root
            other = make_tool_context("it", "two", actor_id="a").workspace_root
            self.assertNotEqual(a, b)
            self.assertNotEqual(a, other)
            (a / "private.txt").write_text("owner only")
            self.assertFalse((b / "private.txt").exists())
            self.assertNotEqual(a, self.root)

    def test_intermediate_calculator_growth_is_bounded(self):
        with self.assertRaises(ValueError):
            _calculate({"expression": "((10**100)**100)**100"}, self.context)


class HttpSecurityTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ, {"ARC_BACKEND_API_KEY": "", "ARC_ENVIRONMENT": "development"}
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.headers = {"X-Arc-Session": str(uuid.uuid4())}

    def test_remote_guest_cannot_use_paid_backend(self):
        with TestClient(app, client=("203.0.113.7", 1234)) as client:
            response = client.get("/company/catalog", headers=self.headers)
        self.assertEqual(response.status_code, 503)

    def test_production_fails_closed_without_key(self):
        with patch.dict(os.environ, {"ARC_ENVIRONMENT": "production"}):
            response = self.client.get("/company/catalog", headers=self.headers)
        self.assertEqual(response.status_code, 503)

    def test_agent_rate_limit_returns_429_not_502(self):
        from fastapi import HTTPException

        with patch(
            "app._enforce_agent_run_rate",
            side_effect=HTTPException(429, "Rate limited"),
        ):
            # Router captures the function object; use its original globals instead.
            with (
                patch.dict(os.environ, {"ARC_AGENT_RUNS_PER_MINUTE": "1"}),
                patch(
                    "company_api.run_ceo_agent",
                    new_callable=AsyncMock,
                    return_value={"message": "ok"},
                ),
            ):
                one = self.client.post(
                    "/company/ceo/run",
                    headers=self.headers,
                    json={"prompt": "hi", "session_id": "s"},
                )
                two = self.client.post(
                    "/company/ceo/run",
                    headers=self.headers,
                    json={"prompt": "hi", "session_id": "s"},
                )
        self.assertEqual(one.status_code, 200)
        self.assertEqual(two.status_code, 429)
        self.assertIn("Retry-After", two.headers)

    def test_body_limit_includes_chunked_without_content_length(self):
        body = json.dumps({"name": "x" * 1_100_000})
        response = self.client.post(
            "/company/humans",
            headers={**self.headers, "Content-Type": "application/json"},
            content=iter([body[:600000].encode(), body[600000:].encode()]),
        )
        self.assertEqual(response.status_code, 413)

    def test_validation_does_not_echo_submitted_secrets(self):
        response = self.client.post(
            "/company/ceo/run",
            headers=self.headers,
            json={"prompt": {"secret": "SYNTHETIC_DO_NOT_ECHO"}, "session_id": "s"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("SYNTHETIC_DO_NOT_ECHO", response.text)

    def test_untrusted_origin_gets_no_access(self):
        response = self.client.options(
            "/company/catalog",
            headers={
                "Origin": "https://attacker.example",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-Arc-Session",
            },
        )
        self.assertNotIn("access-control-allow-origin", response.headers)

    def test_actor_cannot_read_another_actors_human_records(self):
        response = self.client.post(
            "/company/humans",
            headers=self.headers,
            json={"name": "Private Employee", "role": "Engineer", "session_id": "a"},
        )
        self.assertEqual(response.status_code, 201)
        other = {"X-Arc-Session": str(uuid.uuid4())}
        self.assertEqual(
            self.client.get("/company/humans", headers=other).json()["employees"], []
        )
        response = self.client.post(
            "/company/human-tasks",
            headers=other,
            json={
                "session_id": "a",
                "employee_id": response.json()["id"],
                "description": "test",
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_deleted_project_cannot_execute_old_approval(self):
        actor = (
            "guest:"
            + __import__("hashlib")
            .sha256(self.headers["X-Arc-Session"].encode())
            .hexdigest()
        )
        _, pending = asyncio.run(
            dispatch_tool(
                ("calculator",),
                "calculator",
                {"expression": "1+1"},
                ToolContext("finance", "delete-me", actor),
            )
        )
        self.client.delete("/company/sessions/delete-me", headers=self.headers)
        response = self.client.post(
            "/company/approvals/" + pending["approval_id"],
            headers=self.headers,
            json={
                "session_id": "delete-me",
                "approval_token": pending["approval_token"],
                "approve": True,
            },
        )
        self.assertEqual(response.status_code, 404)


class StoreResourceSecurityTests(unittest.TestCase):
    def test_pending_actions_bounded_and_expired_actions_pruned(self):
        store = AgentStore()
        for index in range(150):
            store.create_pending_action(
                {
                    "approval_id": str(index),
                    "actor_id": "a",
                    "expires_at": time.time() - 1,
                }
            )
        store.create_pending_action(
            {"approval_id": "current", "actor_id": "a", "expires_at": time.time() + 60}
        )
        self.assertEqual(len(store.pending), 1)

    def test_human_employee_limit_is_enforced(self):
        store = AgentStore()
        for index in range(100):
            store.add_human_employee("a", str(index), "Engineer")
        with self.assertRaises(RuntimeError):
            store.add_human_employee("a", "overflow", "Engineer")

    def test_private_employee_cannot_be_assigned_to_another_project(self):
        store = AgentStore()
        employee = store.add_human_employee(
            "a", "Employee", "Engineer", session_id="one"
        )
        with self.assertRaises(ValueError):
            store.assign_human_task("a", "two", employee["id"], "Private project")


class RateAndGatewaySecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_rotating_session_ids_does_not_reset_work_limits(self):
        from security_boundary import SecurityBoundaryMiddleware

        async def empty_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = SecurityBoundaryMiddleware(empty_app)
        statuses = []
        for index in range(31):
            messages = []

            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(message):
                messages.append(message)

            await middleware(
                {
                    "type": "http",
                    "method": "POST",
                    "path": "/company/ceo/run",
                    "client": ("203.0.113.5", 1234),
                    "headers": [(b"x-arc-session", str(uuid.uuid4()).encode())],
                },
                receive,
                send,
            )
            statuses.append(messages[0]["status"])
        self.assertEqual(statuses, [200] * 30 + [429])
        self.assertEqual(dict(middleware._active), {})

    async def test_concurrent_work_is_rejected_and_slots_release_on_cancel(self):
        from security_boundary import SecurityBoundaryMiddleware

        started = asyncio.Event()
        release = asyncio.Event()

        async def waiting_app(scope, receive, send):
            started.set()
            await release.wait()

        middleware = SecurityBoundaryMiddleware(waiting_app)

        async def request():
            responses = []

            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(message):
                responses.append(message)

            await middleware(
                {
                    "type": "http",
                    "method": "POST",
                    "path": "/company/ceo/run",
                    "client": ("127.0.0.1", 1),
                    "headers": [],
                },
                receive,
                send,
            )
            return responses

        tasks = [asyncio.create_task(request()) for _ in range(4)]
        await started.wait()
        result = await request()
        self.assertEqual(result[0]["status"], 429)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.assertEqual(dict(middleware._active), {})

    async def test_unprovisioned_actor_cannot_use_global_connector_credentials(self):
        from agent_tools import _connector_call

        with (
            patch.dict(
                os.environ,
                {
                    "ARC_FINANCE_CONNECTOR_URL": "https://gateway.example/finance",
                    "ARC_FINANCE_CONNECTOR_TOKEN": "synthetic-token",
                    "ARC_CONNECTOR_ALLOWED_ACTORS": "guest:approved",
                },
            ),
            patch("agent_tools.httpx.AsyncClient") as client,
        ):
            result = await _connector_call(
                "finance_connector",
                {"operation": "list"},
                ToolContext("finance", "s", "guest:unapproved"),
            )
        client.assert_not_called()
        self.assertEqual(result["status"], "denied")

    async def test_model_tool_fanout_is_bounded_without_breaking_tool_results(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from company.runtime import run_company_agent

        actor = "fanout-" + uuid.uuid4().hex
        calls = [
            SimpleNamespace(
                id="call-" + str(i),
                function=SimpleNamespace(
                    name="calculator", arguments='{"expression":"1+1"}'
                ),
            )
            for i in range(20)
        ]
        message = MagicMock()
        message.tool_calls = calls
        message.content = None
        message.model_dump.return_value = {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": "calculator", "arguments": "{}"},
                }
                for c in calls
            ],
        }
        client = MagicMock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=message)]
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("company.runtime._openrouter_client", return_value=client),
            patch("agent_tools._workspace_root", return_value=Path(directory)),
        ):
            result = await run_company_agent(
                "cto", "Synthetic test", "fanout", actor_id=actor, requested_by="ceo"
            )
        self.assertEqual(len(result["pending_approvals"]), 8)
        messages = get_agent_store().load_session(actor, "cto", "fanout")
        assistant = next(m for m in messages if m.get("tool_calls"))
        tools = [m for m in messages if m["role"] == "tool"]
        self.assertEqual(
            {c["id"] for c in assistant["tool_calls"]},
            {m["tool_call_id"] for m in tools},
        )
        self.assertEqual(
            client.chat.completions.create.call_args.kwargs["max_tokens"], 4096
        )

    async def test_transport_errors_do_not_reach_model_context_or_audit(self):
        import httpx
        from agent_tools import TOOL_REGISTRY, _execute, get_audit_events

        actor = "transport-" + uuid.uuid4().hex
        context = ToolContext("it", "s", actor)
        spec = TOOL_REGISTRY["terminal_run"]
        with patch(
            "agent_tools._connector_call",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError(
                "Internal URL https://private.example/SYNTHETIC_SECRET"
            ),
        ):
            result = await _execute(spec, {"argv": ["git", "status"]}, context)
        self.assertNotIn("private.example", json.dumps(result))
        self.assertNotIn(
            "SYNTHETIC_SECRET", json.dumps(get_audit_events("s", 100, actor))
        )

    async def test_bad_webhook_signatures_fail_without_side_effects(self):
        from github import verify_github_webhook

        with patch.dict(os.environ, {"GITHUB_WEBHOOK_SECRET": "synthetic-secret"}):
            for signature in [
                None,
                "sha256=bad",
                "sha256=" + "0" * 64,
                "sha256=" + "é" * 64,
            ]:
                self.assertFalse(verify_github_webhook(b"{}", signature))

    async def test_deleted_project_revokes_grants_and_queued_jobs(self):
        store = AgentStore()
        store.set_permission("a", "it", "s", "tool", "allow", {}, time.time() + 60, 1)
        store.create_publish_job({"job_id": "j", "actor_id": "a", "session_id": "s"})
        store.delete_company_session_state("a", "s")
        self.assertIsNone(store.get_permission("a", "it", "s", "tool"))
        self.assertIsNone(store.get_publish_job("a", "j"))


if __name__ == "__main__":
    unittest.main()
