import base64
import hashlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from agent_tools import ToolContext, _connector_call, _terminal_run
from terminal_connection import pair_terminal, terminal_is_connected


class TerminalPairingTests(unittest.TestCase):
    def test_gateway_accepts_the_api_workspace_format_and_rejects_another_actor(self):
        from services.terminal_gateway import validate_request

        with tempfile.TemporaryDirectory() as directory:
            grants = Path(directory) / "grants.json"
            actor = "guest:" + "a" * 64
            grants.write_text(json.dumps({"actors": [actor]}))
            body = {
                "operation": "run",
                "actor_id": actor,
                "workspace_id": hashlib.sha256(actor.encode()).hexdigest()[:24]
                + "/"
                + "b" * 24,
                "parameters": {"argv": ["python", "-m", "pytest"]},
            }
            settings = {"grants_file": str(grants)}
            self.assertEqual(
                validate_request(body, settings)["argv"], ["python3", "-m", "pytest"]
            )
            body["workspace_id"] = "c" * 24 + "/" + "b" * 24
            with self.assertRaises(ValueError):
                validate_request(body, settings)

    def test_pairing_is_one_time_and_bound_to_one_workspace_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            grants = Path(directory) / "grants.json"
            code = "synthetic-terminal-pairing-code-for-tests"
            actor = "guest:" + "a" * 64
            other = "guest:" + "b" * 64
            grants.write_text(
                json.dumps(
                    {
                        "actors": [],
                        "pairing_hash": hashlib.sha256(code.encode()).hexdigest(),
                        "expires_at": time.time() + 60,
                        "paired": False,
                    }
                )
            )
            with patch.dict(os.environ, {"ARC_TERMINAL_GRANTS_FILE": str(grants)}):
                with self.assertRaises(ValueError):
                    pair_terminal(actor, "incorrect-code")
                self.assertFalse(terminal_is_connected(actor))
                pair_terminal(actor, code)
                self.assertTrue(terminal_is_connected(actor))
                with self.assertRaises(ValueError):
                    pair_terminal(other, code)
                self.assertFalse(terminal_is_connected(other))
                self.assertNotIn("pairing_hash", json.loads(grants.read_text()))

    def test_expired_pairing_code_never_grants_access(self):
        with tempfile.TemporaryDirectory() as directory:
            grants = Path(directory) / "grants.json"
            grants.write_text(
                json.dumps(
                    {
                        "pairing_hash": hashlib.sha256(b"test").hexdigest(),
                        "expires_at": time.time() - 1,
                        "actors": [],
                    }
                )
            )
            with patch.dict(os.environ, {"ARC_TERMINAL_GRANTS_FILE": str(grants)}):
                with self.assertRaises(ValueError):
                    pair_terminal("guest:" + "a" * 64, "test")


class TerminalSnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_private_supported_files_are_copied_and_host_secrets_are_excluded(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "test_example.py").write_text(
                "def test_example(): assert 2 + 2 == 4\n"
            )
            (root / ".env").write_text("SYNTHETIC_SECRET")
            (root / "private_key.pem").write_text("SYNTHETIC_SECRET")
            (root / "secrets").mkdir()
            (root / "secrets" / "secret.txt").write_text("SYNTHETIC_SECRET")
            (root / ".git").mkdir()
            (root / ".git" / "config").write_text("SYNTHETIC_SECRET")
            (root / "picture.bin").write_bytes(b"not a text file")
            context = ToolContext("it", "project", "guest:" + "a" * 64, root)
            with patch(
                "agent_tools._connector_call", new_callable=AsyncMock, return_value={}
            ) as call:
                await _terminal_run(
                    {"argv": ["python", "-m", "pytest"], "cwd": "."}, context
                )
            sent = call.call_args.args[1]["parameters"]["files"]
            self.assertEqual(set(sent), {"test_example.py"})
            self.assertEqual(
                base64.b64decode(sent["test_example.py"]).decode(),
                (root / "test_example.py").read_text(),
            )
            self.assertNotIn("SYNTHETIC_SECRET", json.dumps(sent))

    async def test_oversized_project_file_is_not_silently_truncated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "large.py").write_text("x" * 20_001)
            with patch("agent_tools._connector_call", new_callable=AsyncMock) as call:
                with self.assertRaises(ValueError):
                    await _terminal_run(
                        {"argv": ["rg", "text", "."]}, ToolContext("it", "p", "a", root)
                    )
                call.assert_not_awaited()

    async def test_terminal_pairing_does_not_grant_cloud_or_finance_access(self):
        with (
            patch.dict(
                os.environ,
                {
                    "ARC_CLOUD_CONNECTOR_URL": "https://example.invalid/cloud",
                    "ARC_CONNECTOR_ALLOWED_ACTORS": "",
                },
            ),
            patch("agent_tools.terminal_is_connected", return_value=True),
        ):
            result = await _connector_call(
                "cloud_connector",
                {"operation": "list"},
                ToolContext("it", "p", "guest:" + "a" * 64),
            )
        self.assertEqual(result["status"], "denied")


if __name__ == "__main__":
    unittest.main()
