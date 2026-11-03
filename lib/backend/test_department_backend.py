import asyncio
import hashlib
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

from agent_store import AgentStore, get_agent_store
from agent_tools import (
    ToolContext,
    _validate_terminal_argv,
    dispatch_tool,
    resolve_pending_action,
    set_tool_permission,
    tool_schemas,
)
from app import plugins_catalog
from company.ceo import _parse_plan, run_ceo_agent
from company.collaboration import (
    company_events,
    company_groups,
    record_agent_report,
    record_delegation,
)
from company.common import ALL_AGENT_TOOLS
from company.organization import PROFILES, allowed_delegate_targets
from company.runtime import agent_details as department_details
from company.runtime import company_catalog as department_catalog
from company_api import build_company_router
from fastapi import FastAPI
from fastapi.testclient import TestClient
from github import consume_github_state, save_github_state


class PluginCatalogTests(unittest.TestCase):
    @patch(
        "app.github_configuration",
        return_value={"oauth": True, "app_worker": True, "webhook": True},
    )
    @patch("app.list_github_connections", return_value=[])
    def test_catalog_exposes_real_installation_types(
        self,
        _connections,
        _configuration,
    ):
        catalog = plugins_catalog("test-user")
        plugins = {item["id"]: item for item in catalog["plugins"]}

        self.assertEqual(len(catalog["plugins"]), len(catalog["tools"]))
        self.assertEqual(plugins["github"]["install_kind"], "github_app")
        self.assertFalse(plugins["github"]["installed"])
        self.assertEqual(
            plugins["finance_connector"]["install_kind"],
            "managed_connector",
        )


class DepartmentRoleTests(unittest.TestCase):
    def test_expected_roles_include_ceo(self):
        self.assertTrue(
            {
                "ceo",
                "cto",
                "manager",
                "finance",
                "marketing",
                "legal",
                "cloud_engineer",
                "ai_engineer",
                "app_developer",
                "it_intern",
            }.issubset(PROFILES)
        )
        self.assertEqual(PROFILES["ceo"].display_name, "Company CEO")
        self.assertEqual(PROFILES["ceo"].provider, "google_ai_studio")
        self.assertTrue(
            all(
                profile.provider == "openrouter"
                for slug, profile in PROFILES.items()
                if slug != "ceo"
            )
        )

    def test_hierarchy_limits_each_leader_to_direct_reports(self):
        self.assertEqual(
            set(allowed_delegate_targets("ceo")),
            {"cto", "manager", "marketing", "finance", "legal"},
        )
        self.assertEqual(
            set(allowed_delegate_targets("cto")),
            {"it", "cloud_engineer", "ai_engineer", "app_developer", "it_intern"},
        )
        self.assertEqual(allowed_delegate_targets("app_developer"), ())

    def test_ceo_plan_rejects_skip_level_delegation(self):
        message, delegations = _parse_plan(
            '{"message":"I will delegate safely.","delegations":['
            '{"agent":"cto","task":"Plan the architecture"},'
            '{"agent":"app_developer","task":"Write the app"}]}'
        )
        self.assertEqual(message, "I will delegate safely.")
        self.assertEqual(
            delegations,
            [{"agent": "cto", "task": "Plan the architecture"}],
        )

    def test_every_enabled_company_agent_has_the_shared_tool_catalog(self):
        for profile in PROFILES.values():
            self.assertEqual(profile.tool_names, ALL_AGENT_TOOLS)
            self.assertIn("terminal_run", profile.tool_names)
            self.assertIn("git_publish", profile.tool_names)

    def test_catalog_contains_tool_risk_information(self):
        catalog = department_catalog()
        self.assertEqual(len(catalog), len(PROFILES))
        it_agent = next(agent for agent in catalog if agent["id"] == "it")
        terminal = next(
            tool for tool in it_agent["tool_details"] if tool["name"] == "terminal_run"
        )
        self.assertEqual(terminal["risk"], "approval_required")

    def test_unknown_department_is_rejected(self):
        with self.assertRaises(ValueError):
            department_details("unknown")

    def test_openai_compatible_schemas_are_generated(self):
        schemas = tool_schemas(("calculator", "workspace_read"))
        self.assertEqual(
            [item["function"]["name"] for item in schemas],
            ["calculator", "workspace_read"],
        )

    def test_git_branch_mutation_is_rejected(self):
        with self.assertRaises(ValueError):
            _validate_terminal_argv(["git", "branch", "-D", "main"])
        self.assertEqual(
            _validate_terminal_argv(["git", "branch", "--show-current"]),
            ["git", "branch", "--show-current"],
        )


class CompanyOrchestrationTests(unittest.IsolatedAsyncioTestCase):
    @patch("company.runtime.run_company_agent", new_callable=AsyncMock)
    @patch("company.ceo._generate", new_callable=AsyncMock)
    async def test_ceo_delegates_to_cto_and_synthesizes_the_report(
        self,
        generate: AsyncMock,
        run_worker: AsyncMock,
    ):
        generate.side_effect = [
            '{"message":"I assigned the technical plan.","delegations":['
            '{"agent":"cto","task":"Design the production architecture"}]}',
            "The CTO designed the production architecture with a rollback plan.",
        ]
        run_worker.return_value = {
            "agent_id": "cto",
            "agent": "Chief Technology Officer",
            "message": "Use a staged deployment with health checks.",
            "pending_approvals": [],
        }

        get_agent_store().save_session(
            "ceo-test-user",
            "project_team",
            "ceo-orchestration",
            {
                "mode": "manual",
                "members": [{"agent_id": "claude", "role_id": "cto"}],
            },
        )

        result = await run_ceo_agent(
            "Create a production technical plan",
            "ceo-orchestration",
            actor_id="ceo-test-user",
        )

        run_worker.assert_awaited_once_with(
            "cto",
            "Design the production architecture",
            "ceo-orchestration",
            delegation_depth=1,
            actor_id="ceo-test-user",
            requested_by="ceo",
        )
        self.assertEqual(result["provider"], "google_ai_studio")
        self.assertEqual(len(result["delegations"]), 1)
        self.assertIn("CTO", result["message"])


class CompanyCollaborationTests(unittest.TestCase):
    def setUp(self):
        self.actor_id = f"collaboration-{uuid.uuid4()}"
        self.session_id = f"session-{uuid.uuid4().hex[:12]}"

    def test_director_builds_a_group_and_adds_an_intern(self):
        group = record_delegation(
            actor_id=self.actor_id,
            session_id=self.session_id,
            sender_id="ceo",
            recipient_id="cto",
            task="Create the technical delivery group.",
        )
        record_delegation(
            actor_id=self.actor_id,
            session_id=self.session_id,
            sender_id="cto",
            recipient_id="it_intern",
            task="Research deployment options and report the evidence.",
            group_id=group["group_id"],
        )
        record_agent_report(
            actor_id=self.actor_id,
            session_id=self.session_id,
            sender_id="it_intern",
            recipient_id="cto",
            content="Research complete; two deployment options were documented.",
            group_id=group["group_id"],
        )
        record_agent_report(
            actor_id=self.actor_id,
            session_id=self.session_id,
            sender_id="cto",
            recipient_id="ceo",
            content="The technology group completed its initial research.",
            group_id=group["group_id"],
        )

        groups = company_groups(self.actor_id, self.session_id)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["director_id"], "cto")
        self.assertEqual(
            {member["agent_id"] for member in groups[0]["members"]},
            {"ceo", "cto", "it_intern"},
        )
        events = company_events(self.actor_id, self.session_id)
        self.assertEqual(
            [event["event_type"] for event in events],
            [
                "group_created",
                "task_delegated",
                "member_added",
                "task_delegated",
                "agent_report",
                "agent_report",
            ],
        )

    def test_agents_cannot_skip_the_reporting_hierarchy(self):
        with self.assertRaises(ValueError):
            record_delegation(
                actor_id=self.actor_id,
                session_id=self.session_id,
                sender_id="ceo",
                recipient_id="it_intern",
                task="Skip the CTO.",
            )
        group = record_delegation(
            actor_id=self.actor_id,
            session_id=self.session_id,
            sender_id="ceo",
            recipient_id="cto",
            task="Create a technology group.",
        )
        with self.assertRaises(ValueError):
            record_delegation(
                actor_id=self.actor_id,
                session_id=self.session_id,
                sender_id="cto",
                recipient_id="accountant",
                task="Cross department boundaries.",
                group_id=group["group_id"],
            )

    def test_group_history_is_scoped_to_the_authenticated_actor(self):
        record_delegation(
            actor_id=self.actor_id,
            session_id=self.session_id,
            sender_id="ceo",
            recipient_id="finance",
            task="Create a finance group.",
        )
        self.assertEqual(company_groups("another-user", self.session_id), [])
        self.assertEqual(company_events("another-user", self.session_id), [])


class ToolPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        get_agent_store().set_approval_mode("local", "ask")

    async def test_ask_mode_requires_approval_even_for_calculator(self):
        context = ToolContext(role="finance", session_id="test-session")
        result, pending = await dispatch_tool(
            ("calculator",),
            "calculator",
            {"expression": "(1200 - 200) / 4"},
            context,
        )
        self.assertEqual(result["status"], "approval_required")
        approved = await resolve_pending_action(
            pending["approval_id"],
            pending["approval_token"],
            "test-session",
            True,
        )
        self.assertEqual(approved["status"], "completed")
        self.assertEqual(approved["output"]["result"], 250)

    async def test_role_cannot_call_unassigned_tool(self):
        context = ToolContext(role="finance", session_id="test-session")
        result, pending = await dispatch_tool(
            ("calculator",),
            "terminal_run",
            {"argv": ["git", "status"]},
            context,
        )
        self.assertIsNone(pending)
        self.assertEqual(result["status"], "denied")

    async def test_cto_cannot_delegate_outside_technology(self):
        get_agent_store().set_approval_mode("local", "allow")
        context = ToolContext(
            role="cto",
            session_id="hierarchy-session",
            delegation_depth=1,
        )
        result, pending = await dispatch_tool(
            ("delegate_agent",),
            "delegate_agent",
            {"agent": "marketing", "task": "Create a campaign"},
            context,
        )
        self.assertIsNone(pending)
        self.assertEqual(result["status"], "failed")
        self.assertIn("direct reports", result["error"])

    async def test_privileged_tool_requires_one_time_approval(self):
        context = ToolContext(role="it", session_id="approval-session")
        result, pending = await dispatch_tool(
            ("terminal_run",),
            "terminal_run",
            {"argv": ["git", "status"]},
            context,
        )
        self.assertEqual(result["status"], "approval_required")
        self.assertIsNotNone(pending)
        denied = await resolve_pending_action(
            approval_id=pending["approval_id"],
            approval_token=pending["approval_token"],
            session_id="approval-session",
            approve=False,
        )
        self.assertEqual(denied["status"], "denied")

    async def test_workspace_reader_blocks_parent_escape(self):
        get_agent_store().set_approval_mode("local", "allow")
        with tempfile.TemporaryDirectory() as directory:
            context = ToolContext(
                role="legal",
                session_id="path-session",
                workspace_root=Path(directory),
            )
            result, pending = await dispatch_tool(
                ("workspace_read",),
                "workspace_read",
                {"path": "../outside.txt"},
                context,
            )
        self.assertIsNone(pending)
        self.assertEqual(result["status"], "failed")
        self.assertIn("escapes", result["error"])

    async def test_workspace_reader_blocks_secret_named_files(self):
        get_agent_store().set_approval_mode("local", "allow")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "client_secret.json").write_text(
                '{"secret": "hidden"}', encoding="utf-8"
            )
            context = ToolContext(
                role="legal",
                session_id="secret-session",
                workspace_root=root,
            )
            result, _ = await dispatch_tool(
                ("workspace_read",),
                "workspace_read",
                {"path": "client_secret.json"},
                context,
            )
        self.assertEqual(result["status"], "failed")
        self.assertIn("secret-bearing", result["error"])

    async def test_approval_is_bound_to_the_authenticated_actor(self):
        context = ToolContext(
            role="it",
            session_id="shared-session-name",
            actor_id="user-a",
        )
        _, pending = await dispatch_tool(
            ("terminal_run",),
            "terminal_run",
            {"argv": ["git", "status"]},
            context,
        )
        with self.assertRaises(PermissionError):
            await resolve_pending_action(
                approval_id=pending["approval_id"],
                approval_token=pending["approval_token"],
                session_id="shared-session-name",
                approve=False,
                actor_id="user-b",
            )
        cleanup = await resolve_pending_action(
            approval_id=pending["approval_id"],
            approval_token=pending["approval_token"],
            session_id="shared-session-name",
            approve=False,
            actor_id="user-a",
        )
        self.assertEqual(cleanup["status"], "denied")

    async def test_global_mode_controls_updates_for_all_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "safe.txt"
            other = root / "other.txt"
            target.write_text("before", encoding="utf-8")
            other.write_text("unchanged", encoding="utf-8")
            actor = f"update-{uuid.uuid4()}"
            get_agent_store().set_approval_mode(actor, "allow")
            session = "scoped-update"
            set_tool_permission(
                actor,
                "it",
                session,
                "workspace_update",
                "allow",
                10,
                2,
                {"paths": ["safe.txt"]},
            )
            context = ToolContext(
                role="it",
                session_id=session,
                actor_id=actor,
                workspace_root=root,
            )
            result, pending = await dispatch_tool(
                ("workspace_update",),
                "workspace_update",
                {
                    "path": "safe.txt",
                    "old_text": "before",
                    "new_text": "after",
                    "expected_sha256": hashlib.sha256(b"before").hexdigest(),
                },
                context,
            )
            self.assertIsNone(pending)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(target.read_text(encoding="utf-8"), "after")

            get_agent_store().set_approval_mode(actor, "ask")

            mismatch, pending = await dispatch_tool(
                ("workspace_update",),
                "workspace_update",
                {"path": "other.txt", "old_text": "unchanged", "new_text": "changed"},
                context,
            )
            self.assertEqual(mismatch["status"], "approval_required")
            self.assertEqual(other.read_text(encoding="utf-8"), "unchanged")
            await resolve_pending_action(
                pending["approval_id"],
                pending["approval_token"],
                session,
                False,
                actor,
            )

    async def test_delete_is_recoverable_and_actor_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "remove.txt"
            target.write_text("recover me", encoding="utf-8")
            actor = f"delete-{uuid.uuid4()}"
            get_agent_store().set_approval_mode(actor, "allow")
            session = "trash-session"
            context = ToolContext("it", session, actor, root)
            set_tool_permission(
                actor,
                "it",
                session,
                "workspace_delete",
                "allow",
                10,
                1,
                {"paths": ["remove.txt"]},
            )
            deleted, pending = await dispatch_tool(
                ("workspace_delete",),
                "workspace_delete",
                {"path": "remove.txt"},
                context,
            )
            self.assertIsNone(pending)
            trash_id = deleted["output"]["trash_id"]
            self.assertFalse(target.exists())

            set_tool_permission(
                actor,
                "it",
                session,
                "workspace_restore",
                "allow",
                10,
                1,
                {"trash_ids": [trash_id]},
            )
            restored, pending = await dispatch_tool(
                ("workspace_restore",),
                "workspace_restore",
                {"trash_id": trash_id},
                context,
            )
            self.assertIsNone(pending)
            self.assertEqual(restored["status"], "completed")
            self.assertEqual(target.read_text(encoding="utf-8"), "recover me")

    async def test_restore_rejects_tampered_trash_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "tamper.txt"
            target.write_text("original", encoding="utf-8")
            actor = f"tamper-{uuid.uuid4()}"
            get_agent_store().set_approval_mode(actor, "allow")
            session = "tamper-session"
            context = ToolContext("it", session, actor, root)
            set_tool_permission(
                actor,
                "it",
                session,
                "workspace_delete",
                "allow",
                10,
                1,
                {"paths": ["tamper.txt"]},
            )
            deleted, _ = await dispatch_tool(
                ("workspace_delete",),
                "workspace_delete",
                {"path": "tamper.txt"},
                context,
            )
            trash_id = deleted["output"]["trash_id"]
            trashed_file = next((root / ".arc" / "trash").rglob("tamper.txt"))
            trashed_file.write_text("changed", encoding="utf-8")
            set_tool_permission(
                actor,
                "it",
                session,
                "workspace_restore",
                "allow",
                10,
                1,
                {"trash_ids": [trash_id]},
            )
            restored, _ = await dispatch_tool(
                ("workspace_restore",),
                "workspace_restore",
                {"trash_id": trash_id},
                context,
            )
            self.assertEqual(restored["status"], "failed")
            self.assertIn("integrity", restored["error"])
            self.assertFalse(target.exists())

    async def test_draft_does_not_overwrite_an_existing_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            actor = f"draft-{uuid.uuid4()}"
            get_agent_store().set_approval_mode(actor, "allow")
            session = "draft-session"
            context = ToolContext("legal", session, actor, root)
            set_tool_permission(
                actor,
                "legal",
                session,
                "draft_file",
                "allow",
                10,
                2,
                {"names": ["review.md"]},
            )
            first, _ = await dispatch_tool(
                ("draft_file",),
                "draft_file",
                {"name": "review.md", "content": "first"},
                context,
            )
            second, _ = await dispatch_tool(
                ("draft_file",),
                "draft_file",
                {"name": "review.md", "content": "second"},
                context,
            )
            self.assertEqual(first["status"], "completed")
            self.assertEqual(second["status"], "failed")
            self.assertEqual(
                (root / ".arc" / "drafts" / "legal" / "review.md").read_text(
                    encoding="utf-8"
                ),
                "first",
            )

    async def test_explicit_deny_is_enforced_even_in_ask_mode(self):
        actor = f"deny-{uuid.uuid4()}"
        set_tool_permission(
            actor, "it", "deny-session", "terminal_run", "deny", 10, 1, {}
        )
        result, pending = await dispatch_tool(
            ("terminal_run",),
            "terminal_run",
            {"argv": ["git", "status"]},
            ToolContext("it", "deny-session", actor),
        )
        self.assertIsNone(pending)
        self.assertEqual(result["status"], "denied")

    async def test_terminal_automatic_scope_requires_exact_arguments(self):
        actor = f"terminal-{uuid.uuid4()}"
        session = "terminal-exact"
        set_tool_permission(
            actor,
            "it",
            session,
            "terminal_run",
            "allow",
            10,
            2,
            {"argv": ["git", "status"]},
        )
        result, pending = await dispatch_tool(
            ("terminal_run",),
            "terminal_run",
            {"argv": ["git", "log"]},
            ToolContext("it", session, actor),
        )
        self.assertEqual(result["status"], "approval_required")
        await resolve_pending_action(
            pending["approval_id"], pending["approval_token"], session, False, actor
        )

    async def test_secret_fields_are_rejected_before_approval_storage(self):
        result, pending = await dispatch_tool(
            ALL_AGENT_TOOLS,
            "crm_connector",
            {"operation": "contact", "parameters": {"api_token": "do-not-store"}},
            ToolContext("marketing", "secret-guard", f"secret-{uuid.uuid4()}"),
            force_one_time_approval=True,
        )
        self.assertIsNone(pending)
        self.assertEqual(result["status"], "denied")

    async def test_publish_tool_queues_manifest_without_claiming_it_pushed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "change.txt").write_text("reviewed", encoding="utf-8")
            actor = f"publish-{uuid.uuid4()}"
            get_agent_store().set_approval_mode(actor, "allow")
            session = "publish-session"
            arguments = {
                "repository": "owner/repository",
                "branch": "main",
                "base_commit": "a" * 40,
                "commit_message": "Apply reviewed change",
                "paths": ["change.txt"],
            }
            set_tool_permission(
                actor,
                "it",
                session,
                "git_publish",
                "allow",
                10,
                1,
                {
                    "repository": "owner/repository",
                    "branch": "main",
                    "paths": ["change.txt"],
                },
            )
            result, pending = await dispatch_tool(
                ("git_publish",),
                "git_publish",
                arguments,
                ToolContext("it", session, actor, root),
            )
            self.assertIsNone(pending)
            self.assertEqual(result["output"]["status"], "queued")
            self.assertFalse(result["output"]["published"])
            jobs = get_agent_store().list_publish_jobs(actor)
            self.assertEqual(jobs[0]["repository"], "owner/repository")


class MemoryStoreTests(unittest.TestCase):
    def test_permission_does_not_survive_a_new_store_instance(self):
        first = AgentStore()
        first.set_permission(
            "actor",
            "it",
            "session",
            "workspace_update",
            "allow",
            {"paths": ["one.txt"]},
            4_000_000_000,
            3,
        )
        second = AgentStore()
        permission = second.get_permission("actor", "it", "session", "workspace_update")
        self.assertIsNone(permission)
        self.assertEqual(
            first.get_permission("actor", "it", "session", "workspace_update")["scope"],
            {"paths": ["one.txt"]},
        )

    def test_github_oauth_state_is_single_use(self):
        state = "s" * 40
        save_github_state(state, "oauth-user")
        self.assertEqual(consume_github_state(state), "oauth-user")
        self.assertIsNone(consume_github_state(state))

    def test_publish_job_transition_is_actor_scoped(self):
        store = get_agent_store()
        job_id = f"job-{uuid.uuid4()}"
        store.create_publish_job(
            {
                "job_id": job_id,
                "actor_id": "job-owner",
                "role": "it",
                "session_id": "job-session",
                "repository": "owner/repository",
                "branch": "main",
                "base_commit": "a" * 40,
                "commit_message": "Reviewed change",
                "paths": ["one.txt"],
                "snapshot": [{"path": "one.txt", "state": "deleted", "sha256": None}],
            }
        )
        self.assertFalse(
            store.transition_publish_job("other-user", job_id, {"queued"}, "cancelled")
        )
        self.assertTrue(
            store.transition_publish_job("job-owner", job_id, {"queued"}, "cancelled")
        )

    def test_github_connections_are_actor_scoped(self):
        store = get_agent_store()
        installation_id = int(uuid.uuid4().int % 1_000_000_000)
        store.save_github_connection(
            actor_id="github-owner",
            installation_id=installation_id,
            account_login="example-owner",
            account_type="User",
            github_user_id="123",
            github_user_login="example-user",
        )
        self.assertEqual(
            store.list_github_connections("github-owner")[0]["installation_id"],
            installation_id,
        )
        self.assertEqual(store.list_github_connections("another-user"), [])
        self.assertFalse(
            store.delete_github_connection("another-user", installation_id)
        )
        self.assertTrue(store.delete_github_connection("github-owner", installation_id))


class CompanyApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_app = FastAPI()
        test_app.include_router(build_company_router(lambda: "api-user"))
        cls.client = TestClient(test_app)

    @patch.dict(
        os.environ,
        {
            "ARC_CEO_PROVIDER": "google_ai_studio",
            "GEMINI_API_KEY": "synthetic-configured-key",
        },
    )
    def test_company_is_a_separate_api_and_ceo_is_ready(self):
        response = self.client.get("/company/catalog")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["product"], "Arc Company")
        self.assertEqual(response.json()["ceo"]["status"], "ready")
        self.assertIn("ceo", {agent["id"] for agent in response.json()["agents"]})
        self.assertEqual(response.json()["publicly_callable_agents"], ["ceo"])
        self.assertEqual(response.json()["organization"]["id"], "ceo")

    def test_internal_agents_cannot_be_called_directly(self):
        response = self.client.post(
            "/company/agents/cto/run",
            json={"prompt": "Build the system", "session_id": "api-session"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("/company/ceo/run", response.json()["detail"])

    def test_automatic_permission_requires_explicit_confirmation(self):
        response = self.client.put(
            "/company/permissions/it/workspace_update",
            json={
                "session_id": "api-session",
                "mode": "allow",
                "scope": {"paths": ["safe.txt"]},
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_one_approval_policy_applies_to_all_tools(self):
        get_agent_store().set_approval_mode("api-user", "ask")
        self.assertEqual(
            self.client.get("/company/approval-policy").json()["mode"], "ask"
        )
        rejected = self.client.put("/company/approval-policy", json={"mode": "allow"})
        self.assertEqual(rejected.status_code, 400)
        allowed = self.client.put(
            "/company/approval-policy",
            json={
                "mode": "allow",
                "confirm_automatic_access": True,
            },
        )
        self.assertEqual(allowed.json()["mode"], "allow")
        self.assertEqual(get_agent_store().get_approval_mode("api-user"), "allow")
        self.client.put("/company/approval-policy", json={"mode": "ask"})

    def test_human_employee_and_draft_task_are_actor_scoped(self):
        created = self.client.post(
            "/company/humans",
            json={
                "name": "Alex",
                "role": "Designer",
            },
        )
        self.assertEqual(created.status_code, 201)
        employee_id = created.json()["id"]
        self.assertIn(
            employee_id,
            {
                person["id"]
                for person in self.client.get("/company/humans").json()["employees"]
            },
        )
        assigned = self.client.post(
            "/company/human-tasks",
            json={
                "session_id": "company-1",
                "employee_id": employee_id,
                "description": "Review the homepage",
            },
        )
        self.assertEqual(assigned.status_code, 201)
        self.assertEqual(assigned.json()["status"], "draft_assignment")
        self.assertEqual(
            len(
                self.client.get("/company/human-tasks?session_id=company-1").json()[
                    "tasks"
                ]
            ),
            1,
        )
        self.assertEqual(
            self.client.get("/company/human-tasks?session_id=company-2").json()[
                "tasks"
            ],
            [],
        )

    def test_pending_actions_can_be_reviewed_from_settings(self):
        get_agent_store().set_approval_mode("api-user", "ask")
        result, pending = asyncio.run(
            dispatch_tool(
                ("calculator",),
                "calculator",
                {"expression": "8 * 7"},
                ToolContext("finance", "settings-session", "api-user"),
            )
        )
        self.assertEqual(result["status"], "approval_required")
        requests = self.client.get("/company/approval-requests").json()["requests"]
        item = next(
            request
            for request in requests
            if request["approval_id"] == pending["approval_id"]
        )
        self.assertNotIn("approval_token", item)
        decision = self.client.post(
            f"/company/approval-requests/{pending['approval_id']}",
            json={
                "session_id": "settings-session",
                "approve": True,
            },
        )
        self.assertEqual(decision.status_code, 200)
        self.assertEqual(decision.json()["output"]["result"], 56)

    def test_frontend_can_read_groups_and_events_but_not_run_workers(self):
        session_id = f"api-group-{uuid.uuid4().hex[:10]}"
        group = record_delegation(
            actor_id="api-user",
            session_id=session_id,
            sender_id="ceo",
            recipient_id="cto",
            task="Build the technology group.",
        )
        record_delegation(
            actor_id="api-user",
            session_id=session_id,
            sender_id="cto",
            recipient_id="cloud_engineer",
            task="Prepare the deployment architecture.",
            group_id=group["group_id"],
        )

        groups_response = self.client.get(f"/company/sessions/{session_id}/groups")
        self.assertEqual(groups_response.status_code, 200)
        self.assertEqual(groups_response.json()["user_can_message"], ["ceo"])
        self.assertEqual(groups_response.json()["groups"][0]["director_id"], "cto")

        events_response = self.client.get(f"/company/sessions/{session_id}/events")
        self.assertEqual(events_response.status_code, 200)
        self.assertTrue(events_response.json()["read_only"])
        self.assertGreaterEqual(len(events_response.json()["events"]), 4)

        worker_response = self.client.post(
            "/company/agents/cloud_engineer/run",
            json={"prompt": "Run directly", "session_id": session_id},
        )
        self.assertEqual(worker_response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
