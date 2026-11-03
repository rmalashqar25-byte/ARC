import asyncio
import json
import os
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from company.ceo import run_ceo_agent
from company.runtime import clear_company_session, run_company_agent
from company.team import assignment, get_team, save_team


class ProjectTeamTests(unittest.TestCase):
    def setUp(self):
        self.actor = str(uuid.uuid4())
        self.session = str(uuid.uuid4())
        self.env = patch.dict(
            os.environ,
            {
                "OPENROUTER_API_KEY": "test-only",
                "ARC_MARKET_CLAUDE_MODEL": "anthropic/test-claude",
                "ARC_MARKET_GPT_SOL_MODEL": "openai/test-sol",
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_team_is_actor_and_project_scoped_and_deleted_with_project(self):
        save_team(
            self.actor,
            self.session,
            "manual",
            [{"agent_id": "claude", "role_id": "cto"}],
        )
        self.assertEqual(
            assignment(self.actor, self.session, "cto")["model"],
            "anthropic/test-claude",
        )
        self.assertEqual(get_team("other", self.session)["members"], [])
        self.assertEqual(get_team(self.actor, "other")["members"], [])
        clear_company_session(self.session, self.actor)
        self.assertEqual(get_team(self.actor, self.session)["mode"], "undecided")

    def test_unconfigured_and_duplicate_hires_do_not_replace_the_team(self):
        save_team(self.actor, self.session, "ceo", [])
        with patch.dict(os.environ, {"ARC_MARKET_CLAUDE_MODEL": ""}):
            with self.assertRaises(ValueError):
                save_team(
                    self.actor,
                    self.session,
                    "manual",
                    [{"agent_id": "claude", "role_id": "cto"}],
                )
        with self.assertRaises(ValueError):
            save_team(
                self.actor,
                self.session,
                "manual",
                [
                    {"agent_id": "claude", "role_id": "cto"},
                    {"agent_id": "gpt_sol", "role_id": "cto"},
                ],
            )
        self.assertEqual(
            get_team(self.actor, self.session), {"mode": "ceo", "members": []}
        )

    def test_runtime_uses_hired_model_and_blocks_unhired_roles(self):
        save_team(
            self.actor,
            self.session,
            "manual",
            [{"agent_id": "claude", "role_id": "cto"}],
        )
        client = MagicMock()
        message = SimpleNamespace(
            content="Technical plan",
            tool_calls=[],
            model_dump=lambda **_: {"role": "assistant", "content": "Technical plan"},
        )
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=message)]
        )
        with patch("company.runtime._openrouter_client", return_value=client):
            result = asyncio.run(
                run_company_agent(
                    "cto",
                    "Build the app",
                    self.session,
                    actor_id=self.actor,
                    requested_by="ceo",
                )
            )
        self.assertEqual(
            client.chat.completions.create.call_args.kwargs["model"],
            "anthropic/test-claude",
        )
        self.assertEqual(result["agent"], "Claude")
        with self.assertRaises(ValueError):
            asyncio.run(
                run_company_agent(
                    "manager",
                    "Plan",
                    self.session,
                    actor_id=self.actor,
                    requested_by="ceo",
                )
            )

    def test_ceo_waits_for_choice_and_can_choose_a_persistent_team(self):
        plan = {
            "message": "Would you like to choose your agents or let me choose?",
            "delegations": [{"agent": "cto", "task": "Build"}],
        }
        with (
            patch(
                "company.ceo._generate",
                new_callable=AsyncMock,
                return_value=json.dumps(plan),
            ),
            patch(
                "company.runtime.run_company_agent", new_callable=AsyncMock
            ) as worker,
        ):
            asyncio.run(
                run_ceo_agent("Build my company", self.session, actor_id=self.actor)
            )
            worker.assert_not_awaited()
        plan.update(team_mode="ceo", team=[{"agent_id": "claude", "role_id": "cto"}])
        with (
            patch(
                "company.ceo._generate",
                new_callable=AsyncMock,
                return_value=json.dumps(plan),
            ),
            patch(
                "company.runtime.run_company_agent",
                new_callable=AsyncMock,
                return_value={"message": "Built", "pending_approvals": []},
            ) as worker,
        ):
            asyncio.run(
                run_ceo_agent("Choose for me", self.session, actor_id=self.actor)
            )
            worker.assert_awaited_once()
        self.assertEqual(get_team(self.actor, self.session)["members"], plan["team"])


if __name__ == "__main__":
    unittest.main()
