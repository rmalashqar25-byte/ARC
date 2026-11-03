import asyncio
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from agent_store import AgentStore
from agent_tools import ToolContext, dispatch_tool
from company.work_api import build_work_router
from company.work_policy import WORK_SCOPE, local_permission, model_gate
from company.work_runtime import CompanyWorker
from company.work_store import WorkStore
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

FREE = {
    "model_id": "vendor/real-test:free",
    "id": "vendor/real-test:free",
    "name": "Free test model",
    "configured": True,
    "input_price_per_million": 0,
    "output_price_per_million": 0,
    "agent_compatible": True,
}


class CompanyWorkTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.db = WorkStore(self.root / "work.sqlite")
        self.store = AgentStore()
        self.store.bind_work_store(self.db)
        for module in (
            "company_api",
            "company.work_api",
            "company.work_runtime",
            "company.human_work",
            "company.human_planning",
            "company.team",
            "company.runtime",
            "company.ceo",
            "company.collaboration",
            "agent_tools",
        ):
            self.stack.enter_context(
                patch(module + ".get_agent_store", return_value=self.store)
            )
        self.stack.enter_context(
            patch("company.work_api.work_models", return_value=[FREE])
        )

        def access(x_actor: str = Header(default="")):
            if not x_actor:
                raise HTTPException(401, "Founder access required")
            return x_actor

        app = FastAPI()
        app.include_router(build_work_router(access))
        self.api = self.stack.enter_context(TestClient(app))
        self.headers = {"X-Actor": "founder"}
        self.path = "/company/sessions/project/work"

    def enable(self):
        self.db.configure("founder", "project", True, FREE["model_id"])

    def task(self, **changes):
        return self.db.create(
            "founder",
            "project",
            title="A bounded task",
            description="Do the assigned work",
            **changes,
        )

    def employee(self, name="Alex", capacity=1):
        return self.store.add_human_employee(
            "founder", name, "Researcher", session_id="project", job_capacity=capacity
        )

    def offer(self, person):
        return self.api.post(
            self.path + "/tasks",
            headers=self.headers,
            json={
                "title": "Write findings",
                "description": "Write an evidence-backed research summary.",
                "kind": "human",
                "assignee": person["id"],
            },
        )

    def invitation(self, person):
        token = self.api.post(
            self.path + "/invites/" + person["id"], headers=self.headers
        ).json()["token"]
        return {"X-Arc-Worker": token}

    def test_persistence_recovers_company_state_but_not_execution_approvals(self):
        self.enable()
        job = self.task()
        self.store.save_session(
            "founder", "project_team", "project", {"mode": "manual", "members": []}
        )
        self.store.set_approval_mode("founder", "allow")
        self.store.create_pending_action(
            {
                "approval_id": "private-approval",
                "actor_id": "founder",
                "expires_at": 10**12,
                "token_digest": "private-token",
            }
        )
        self.store.set_permission(
            "founder", "cto", "project", "terminal_run", "deny", {}, 10**12, 0
        )
        self.store.set_permission(
            "founder", "cto", "project", "workspace_read", "allow", {}, 10**12, 5
        )
        restored = AgentStore()
        restored.bind_work_store(WorkStore(self.db.path))
        self.assertEqual(
            restored.get_permission("founder", "cto", "project", "terminal_run")[
                "mode"
            ],
            "deny",
        )
        self.assertEqual(
            restored.get_permission("founder", "cto", "project", "workspace_read")[
                "mode"
            ],
            "ask",
        )
        self.assertEqual(
            restored.load_session("founder", "project_team", "project")["mode"],
            "manual",
        )
        self.assertEqual(restored.get_approval_mode("founder"), "ask")
        self.assertEqual(restored.pending, {})
        self.assertNotIn("private-token", json.dumps(self.db.load_state()))
        self.assertEqual(
            WorkStore(self.db.path).get("founder", "project", job["id"])["status"],
            "queued",
        )

    def test_paid_model_choice_requires_consent_and_blocks_higher_rates(self):
        paid = dict(
            FREE,
            model_id="vendor/paid",
            id="vendor/paid",
            name="Paid model",
            input_price_per_million=1,
            output_price_per_million=4,
        )
        cheaper = dict(
            paid,
            model_id="vendor/cheaper",
            id="vendor/cheaper",
            input_price_per_million=0.5,
        )
        costly = dict(
            paid,
            model_id="vendor/expensive",
            id="vendor/expensive",
            output_price_per_million=5,
        )
        models = [FREE, paid, cheaper, costly]
        with patch("company.work_api.work_models", return_value=models):
            board = self.api.get(self.path, headers=self.headers).json()
            self.assertFalse(board["free_only"])
            self.assertEqual(len(board["models"]), 4)
            settings = {
                "enabled": True,
                "model": paid["model_id"],
                "confirm_local_autonomy": True,
            }
            self.assertEqual(
                self.api.put(
                    self.path, headers=self.headers, json=settings
                ).status_code,
                400,
            )
            settings["confirm_paid_model"] = True
            self.assertEqual(
                self.api.put(
                    self.path, headers=self.headers, json=settings
                ).status_code,
                200,
            )
        recovered = WorkStore(self.db.path)
        self.assertEqual(
            recovered.company("founder", "project")["price_limits"][
                "output_price_per_million"
            ],
            4,
        )
        token = WORK_SCOPE.set(
            {
                "actor": "founder",
                "session": "project",
                "model": paid["model_id"],
                "database": recovered,
            }
        )
        try:
            with patch("company.model_catalog.catalog", return_value=models):
                model_gate(paid["model_id"])
                model_gate(cheaper["model_id"])
                with self.assertRaises(ValueError):
                    model_gate(costly["model_id"])
                with self.assertRaises(ValueError):
                    model_gate("vendor/unknown")
            price_increase = dict(paid, output_price_per_million=6)
            with patch("company.model_catalog.catalog", return_value=[price_increase]):
                with self.assertRaises(ValueError):
                    model_gate(paid["model_id"])
            recovered.configure("founder", "project", True, FREE["model_id"])
            with patch("company.model_catalog.catalog", return_value=models):
                with self.assertRaises(ValueError):
                    model_gate(paid["model_id"])
        finally:
            WORK_SCOPE.reset(token)

    def test_paused_scheduler_keeps_the_selected_chat_model_without_running_tools(self):
        from company_api import build_company_router

        self.db.configure("founder", "project", False, FREE["model_id"])

        async def chat(**kwargs):
            scope = WORK_SCOPE.get()
            self.assertEqual(scope["model"], FREE["model_id"])
            self.assertTrue(scope["interactive"])
            model_gate(FREE["model_id"])
            self.assertEqual(
                local_permission("founder", "project", "terminal_run"), "deny"
            )
            return {"message": "Selected model is responding"}

        app = FastAPI()
        app.include_router(build_company_router(lambda: "founder"))
        with (
            TestClient(app) as api,
            patch("company_api.run_ceo_agent", new=chat),
            patch("company.model_catalog.catalog", return_value=[FREE]),
        ):
            for path in ("/company/ceo/run", "/company/agents/ceo/run"):
                reply = api.post(
                    path, json={"session_id": "project", "prompt": "Hello"}
                )
                self.assertEqual(reply.status_code, 200)
        self.assertFalse(self.db.company("founder", "project")["enabled"])
        self.assertIsNone(self.db.claim())

    def test_saving_paid_chat_model_requires_consent_even_with_scheduler_paused(self):
        paid = dict(
            FREE,
            model_id="vendor/paid",
            id="vendor/paid",
            input_price_per_million=1,
            output_price_per_million=4,
        )
        with patch("company.work_api.work_models", return_value=[paid]):
            settings = {"enabled": False, "model": paid["model_id"]}
            self.assertEqual(
                self.api.put(
                    self.path, headers=self.headers, json=settings
                ).status_code,
                400,
            )
            settings["confirm_paid_model"] = True
            self.assertEqual(
                self.api.put(
                    self.path, headers=self.headers, json=settings
                ).status_code,
                200,
            )
            settings["confirm_paid_model"] = False
            self.assertEqual(
                self.api.put(
                    self.path, headers=self.headers, json=settings
                ).status_code,
                200,
            )
        self.assertEqual(
            self.db.company("founder", "project")["price_limits"][
                "output_price_per_million"
            ],
            4,
        )
        self.assertFalse(self.db.company("founder", "project")["enabled"])

    def test_existing_company_database_migrates_without_enabling_paid_models(self):
        import sqlite3

        path = self.root / "old.sqlite"
        with sqlite3.connect(path) as connection:
            connection.execute(
                "CREATE TABLE companies (actor TEXT, session TEXT, enabled INTEGER, model TEXT, PRIMARY KEY(actor,session))"
            )
            connection.execute(
                "INSERT INTO companies VALUES (?,?,?,?)",
                ("founder", "project", 1, FREE["model_id"]),
            )
        connection.close()
        migrated = WorkStore(path).company("founder", "project")
        self.assertEqual(migrated["enabled"], 1)
        self.assertEqual(migrated["model"], FREE["model_id"])
        self.assertEqual(migrated["price_limits"], {})

    def test_one_claim_per_company_and_crash_recovery_is_bounded(self):
        self.enable()
        first = self.task()
        self.task()
        with ThreadPoolExecutor(max_workers=4) as pool:
            claimed = list(
                pool.map(lambda _: self.db.claim(now=first["created"] + 1), range(4))
            )
        self.assertEqual(sum(j is not None for j in claimed), 1)
        recovered = self.db.claim(now=first["created"] + 302)
        self.assertEqual(recovered["id"], first["id"])
        self.assertEqual(recovered["attempts"], 2)
        self.db.claim(now=first["created"] + 604)
        self.db.claim(now=first["created"] + 906)
        self.assertEqual(
            self.db.get("founder", "project", first["id"])["status"], "blocked"
        )

    def test_idle_ticks_are_silent_and_completed_jobs_are_not_repeated(self):
        async def scenario():
            executor = AsyncMock(return_value={"message": "Result is ready."})
            worker = CompanyWorker(self.db, executor)
            self.enable()
            for _ in range(4):
                await worker.tick()
            executor.assert_not_awaited()
            self.assertEqual(self.store.events, [])
            task = self.task()
            await worker.tick()
            await asyncio.gather(*list(worker.active))
            self.assertEqual(
                self.db.get("founder", "project", task["id"])["status"], "completed"
            )
            before = len(self.store.events)
            await worker.tick()
            executor.assert_awaited_once()
            self.assertEqual(len(self.store.events), before)

        asyncio.run(scenario())

    def test_claims_without_a_required_passing_check_do_not_count_as_finished(self):
        async def scenario():
            self.enable()
            task = self.task(requires_check=True)
            worker = CompanyWorker(
                self.db,
                AsyncMock(return_value={"message": "All tests pass, trust me."}),
            )
            await worker.tick()
            await asyncio.gather(*list(worker.active))
            self.assertEqual(
                self.db.get("founder", "project", task["id"])["status"], "blocked"
            )

        asyncio.run(scenario())

    def test_pause_and_free_budget_are_enforced_before_model_requests(self):
        self.enable()
        token = WORK_SCOPE.set(
            {
                "actor": "founder",
                "session": "project",
                "model": FREE["model_id"],
                "database": self.db,
            }
        )
        self.addCleanup(WORK_SCOPE.reset, token)
        with patch("company.model_catalog.catalog", return_value=[FREE]):
            for _ in range(36):
                model_gate(FREE["model_id"])
            with self.assertRaises(ValueError):
                model_gate(FREE["model_id"])
            with self.assertRaises(ValueError):
                model_gate("vendor/paid")
        self.db.configure("founder", "project", False, FREE["model_id"])
        self.assertEqual(local_permission("founder", "project", "terminal_run"), "deny")
        self.assertIsNone(local_permission("other", "project", "terminal_run"))

    def test_local_autonomy_does_not_allow_external_tools_or_override_denies(self):
        async def scenario():
            self.enable()
            token = WORK_SCOPE.set(
                {
                    "actor": "founder",
                    "session": "project",
                    "model": FREE["model_id"],
                    "database": self.db,
                    "task_id": "test",
                }
            )
            try:
                context = ToolContext("cto", "project", "founder", self.root)
                output, pending = await dispatch_tool(
                    ("calculator",), "calculator", {"expression": "6*7"}, context
                )
                self.assertEqual(output["output"]["result"], 42)
                self.assertIsNone(pending)
                self.assertEqual(self.store.get_approval_mode("founder"), "ask")
                self.assertEqual(
                    local_permission("founder", "project", "cloud_connector"), "deny"
                )
                self.store.set_permission(
                    "founder", "cto", "project", "calculator", "deny", {}, 10**12, 1
                )
                denied, _ = await dispatch_tool(
                    ("calculator",), "calculator", {"expression": "6*7"}, context
                )
                self.assertEqual(denied["status"], "denied")
            finally:
                WORK_SCOPE.reset(token)

        asyncio.run(scenario())

    def test_human_capacity_group_and_private_portal_access(self):
        alex = self.employee()
        maya = self.employee("Maya")
        one = self.offer(alex)
        self.assertEqual(one.status_code, 201)
        self.assertEqual(self.offer(alex).status_code, 400)
        other = self.offer(maya).json()
        worker = self.invitation(alex)
        own = self.api.get("/work/tasks", headers=worker).json()
        self.assertEqual([t["id"] for t in own["tasks"]], [one.json()["id"]])
        self.assertEqual(own["person"]["active_jobs"], 1)
        self.assertEqual(own["person"]["job_capacity"], 1)
        self.assertEqual(len(own["groups"]), 1)
        self.assertNotIn("events", own)
        self.assertNotIn("actor", own["tasks"][0])
        self.assertEqual(
            self.api.post(
                "/work/tasks/" + other["id"] + "/accept", headers=worker
            ).status_code,
            404,
        )
        self.assertEqual(self.api.get(self.path, headers=worker).status_code, 401)
        groups = self.store.list_company_groups("founder", "project")
        self.assertTrue(
            any(m.get("display_name") == "Alex" for g in groups for m in g["members"])
        )
        self.api.post("/work/tasks/" + one.json()["id"] + "/decline", headers=worker)
        self.assertEqual(self.offer(alex).status_code, 201)

    def test_human_accept_submit_review_and_invitation_revocation(self):
        person = self.employee()
        job = self.offer(person).json()
        worker = self.invitation(person)
        path = "/work/tasks/" + job["id"]
        self.assertEqual(
            self.api.post(
                path + "/submit", headers=worker, json={"content": "My report"}
            ).status_code,
            409,
        )
        self.assertEqual(
            self.api.post(path + "/accept", headers=worker).status_code, 200
        )
        submitted = self.api.post(
            path + "/submit",
            headers=worker,
            json={"content": "Completed report with evidence."},
        )
        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(submitted.json()["status"], "submitted")
        self.assertEqual(
            len(
                [t for t in self.db.list("founder", "project") if t["kind"] == "review"]
            ),
            1,
        )
        self.assertEqual(
            self.api.post(
                path + "/submit", headers=worker, json={"content": "Duplicate"}
            ).status_code,
            409,
        )
        review = self.api.post(
            self.path + "/tasks/" + job["id"] + "/review",
            headers=self.headers,
            json={"decision": "changes_requested", "feedback": "Add sources."},
        )
        self.assertEqual(review.status_code, 200)
        self.assertEqual(
            self.api.get("/work/tasks", headers=worker).json()["tasks"][0]["feedback"],
            "Add sources.",
        )
        self.assertNotIn(worker["X-Arc-Worker"].encode(), self.db.path.read_bytes())
        self.api.delete(self.path + "/invites/" + person["id"], headers=self.headers)
        self.assertEqual(self.api.get("/work/tasks", headers=worker).status_code, 401)

    def test_capacity_is_atomic_and_zero_slots_block_new_work(self):
        self.assertEqual(self.offer(self.employee(capacity=0)).status_code, 400)

        def create(_):
            try:
                return self.db.create(
                    "founder",
                    "project",
                    title="Offer",
                    description="Work",
                    kind="human",
                    assignee="same",
                    human_capacity=1,
                )["id"]
            except ValueError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(create, range(2)))
        self.assertEqual(sum(r is not None for r in results), 1)

    def test_another_founder_cannot_read_or_invite_my_employee(self):
        person = self.employee()
        self.offer(person)
        headers = {"X-Actor": "other"}
        self.assertEqual(self.api.get(self.path, headers=headers).json()["tasks"], [])
        self.assertEqual(
            self.api.post(
                self.path + "/invites/" + person["id"], headers=headers
            ).status_code,
            404,
        )

    def test_manager_reviews_only_the_assigned_deliverable(self):
        self.enable()
        person = self.employee()
        job = self.offer(person).json()
        worker = self.invitation(person)
        path = "/work/tasks/" + job["id"]
        self.api.post(path + "/accept", headers=worker)
        self.api.post(
            path + "/submit",
            headers=worker,
            json={"content": "A focused report for this assigned job."},
        )
        # Recover a submission saved just before a process stopped creating its review.
        with self.db.connection() as db:
            db.execute("DELETE FROM tasks WHERE kind='review'")

        async def scenario():
            with (
                patch(
                    "company.model_catalog.refresh_catalog",
                    new=AsyncMock(return_value=False),
                ),
                patch("company.model_catalog.catalog", return_value=[FREE]),
                patch(
                    "company.ceo._generate",
                    new=AsyncMock(
                        return_value='{"decision":"accepted","feedback":"Meets the brief."}'
                    ),
                ) as review,
            ):
                runtime = CompanyWorker(self.db)
                await runtime.tick()
                await asyncio.gather(*list(runtime.active))
                payload = json.loads(review.call_args.kwargs["prompt"])
                self.assertEqual(set(payload), {"brief", "deliverable"})
                self.assertEqual(
                    payload["deliverable"], "A focused report for this assigned job."
                )

        asyncio.run(scenario())
        own = self.api.get("/work/tasks", headers=worker).json()
        self.assertEqual(own["tasks"][0]["status"], "accepted")
        self.assertEqual(own["tasks"][0]["feedback"], "Meets the brief.")
        self.assertEqual(own["person"]["active_jobs"], 0)

    def test_agent_job_memory_is_private_but_tools_use_the_assigned_project(self):
        from company.runtime import run_company_agent

        self.enable()
        tool = SimpleNamespace(
            id="call",
            function=SimpleNamespace(
                name="calculator", arguments='{"expression":"6*7"}'
            ),
        )
        first = SimpleNamespace(
            content=None,
            tool_calls=[tool],
            model_dump=lambda **_: {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call",
                        "type": "function",
                        "function": {
                            "name": "calculator",
                            "arguments": '{"expression":"6*7"}',
                        },
                    }
                ],
            },
        )
        last = SimpleNamespace(
            content="Result: 42",
            tool_calls=[],
            model_dump=lambda **_: {"role": "assistant", "content": "Result: 42"},
        )
        client = MagicMock()
        client.with_options.return_value = client
        client.chat.completions.create.side_effect = [
            SimpleNamespace(choices=[SimpleNamespace(message=first)]),
            SimpleNamespace(choices=[SimpleNamespace(message=last)]),
        ]

        async def scenario():
            token = WORK_SCOPE.set(
                {
                    "actor": "founder",
                    "session": "project",
                    "model": FREE["model_id"],
                    "database": self.db,
                    "task_id": "isolated-job",
                }
            )
            try:
                with (
                    patch.dict(
                        "os.environ", {"ARC_AGENT_WORKSPACE_ROOT": str(self.root)}
                    ),
                    patch("company.runtime._openrouter_client", return_value=client),
                    patch("company.work_policy.model_gate"),
                    patch(
                        "company.team.get_team",
                        return_value={"mode": "undecided", "members": []},
                    ),
                    patch("company.team.assignment", return_value=None),
                    patch(
                        "company.runtime.dispatch_tool",
                        new=AsyncMock(
                            return_value=(
                                {"status": "completed", "output": {"result": 42}},
                                None,
                            )
                        ),
                    ) as dispatch,
                ):
                    await run_company_agent(
                        "cto",
                        "Calculate this assigned job",
                        "project",
                        actor_id="founder",
                        requested_by="ceo",
                    )
                    self.assertEqual(dispatch.call_args.args[3].session_id, "project")
            finally:
                WORK_SCOPE.reset(token)

        asyncio.run(scenario())
        self.assertIsNotNone(
            self.store.load_session("founder", "cto", "project:isolated-job")
        )
        self.assertIsNone(self.store.load_session("founder", "cto", "project"))

    def test_ceo_queues_paused_work_without_calling_a_specialist_or_synthesis(self):
        from company.ceo import run_ceo_agent

        self.store.save_session(
            "founder",
            "project_team",
            "project",
            {
                "mode": "manual",
                "members": [
                    {
                        "role_id": "cto",
                        "agent_id": FREE["model_id"],
                        "model": FREE["model_id"],
                        "name": "Test lead",
                    }
                ],
            },
        )
        generate = AsyncMock(
            return_value=json.dumps(
                {
                    "message": "Planning",
                    "delegations": [
                        {"agent": "cto", "task": "Build a small demo and test it."}
                    ],
                }
            )
        )
        with (
            patch("company.ceo._generate", new=generate),
            patch("company.runtime.run_company_agent", new=AsyncMock()) as specialist,
        ):
            result = asyncio.run(
                run_ceo_agent("Build the demo", "project", actor_id="founder")
            )
        self.assertEqual(generate.await_count, 1)
        specialist.assert_not_awaited()
        self.assertEqual(result["delegations"][0]["result"]["status"], "queued")
        self.assertIn("paused", result["message"])
        self.assertIn("not been completed", result["message"])
        self.assertIsNone(self.db.claim())
        self.enable()
        self.assertEqual(self.db.claim()["assignee"], "cto")

    def test_employee_delegation_preserves_manager_group_and_job_parent(self):
        from agent_tools import _delegate_agent
        from company.collaboration import ensure_director_group

        self.enable()
        group = ensure_director_group("founder", "project", "cto", "Build a demo")
        parent = self.task(assignee="cto", requires_check=True)
        token = WORK_SCOPE.set(
            {
                "actor": "founder",
                "session": "project",
                "model": FREE["model_id"],
                "database": self.db,
                "task_id": parent["id"],
                "requires_check": True,
            }
        )
        try:
            context = ToolContext(
                "cto",
                "project",
                "founder",
                self.root,
                delegation_depth=1,
                company_group_id=group["group_id"],
            )
            result = asyncio.run(
                _delegate_agent(
                    {"agent": "app_developer", "task": "Implement and test"}, context
                )
            )
            self.assertEqual(result["status"], "queued")
            child = self.db.get("founder", "project", result["work_task_id"])
            self.assertEqual(child["manager"], "cto")
            self.assertEqual(child["group_id"], group["group_id"])
            self.assertEqual(child["parent"], parent["id"])
            self.assertTrue(child["requires_check"])
            with (
                patch("company.model_catalog.refresh_catalog", new=AsyncMock()),
                patch(
                    "company.runtime.run_company_agent",
                    new=AsyncMock(return_value={"message": "Done"}),
                ) as specialist,
            ):
                asyncio.run(CompanyWorker(self.db).execute(child))
                self.assertEqual(
                    specialist.call_args.kwargs["group_id"], group["group_id"]
                )
        finally:
            WORK_SCOPE.reset(token)

    def test_agent_step_limit_becomes_blocked_work_instead_of_a_connection_error(self):
        from company.runtime import run_company_agent

        with (
            patch("company.runtime.MAX_AGENT_STEPS", 0),
            patch(
                "company.team.get_team",
                return_value={"mode": "undecided", "members": []},
            ),
            patch("company.team.assignment", return_value=None),
        ):
            result = asyncio.run(
                run_company_agent(
                    "cto",
                    "Fix the task",
                    "project",
                    actor_id="founder",
                    requested_by="ceo",
                )
            )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "step_limit")
        self.assertIn("incomplete", result["message"])
        self.enable()
        job = self.task()
        running = self.db.claim()
        asyncio.run(
            CompanyWorker(self.db, AsyncMock(return_value=result)).process(running)
        )
        self.assertEqual(
            self.db.get("founder", "project", job["id"])["status"], "blocked"
        )

    def test_delegated_company_job_waits_for_its_team_and_verification(self):
        self.enable()
        parent = self.task(requires_check=True)
        running = self.db.claim()

        async def execute(_):
            self.db.create(
                "founder",
                "project",
                title="Implementation",
                description="Fix and verify",
                assignee="cto",
                parent=parent["id"],
                requires_check=True,
            )
            return {
                "message": "Assigned to the team.",
            }

        asyncio.run(CompanyWorker(self.db, execute).process(running))
        self.assertEqual(
            self.db.get("founder", "project", parent["id"])["status"], "waiting_team"
        )
        child = next(
            t
            for t in self.db.list("founder", "project")
            if t.get("parent") == parent["id"]
        )
        self.db.update(
            "founder",
            "project",
            child["id"],
            status="completed",
            result="Verified passing check",
            verified_check=True,
        )
        changed = self.db.reconcile_parents()
        self.assertEqual(changed[0]["status"], "completed")
        self.assertTrue(changed[0]["verified_check"])
