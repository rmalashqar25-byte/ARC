import os
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from agent_store import AgentStore
from app import app
from auth_service import resolve_session_actor
from fastapi.testclient import TestClient


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"ARC_BACKEND_API_KEY": ""})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.token = str(uuid.uuid4())

    def test_guest_can_load_catalog_without_account(self):
        result = self.client.get(
            "/company/catalog", headers={"X-Arc-Session": self.token}
        )
        self.assertEqual(result.status_code, 200)

    def test_missing_or_malformed_session_is_rejected(self):
        for token in ("", "user", str(uuid.uuid1())):
            self.assertEqual(
                self.client.get(
                    "/company/catalog", headers={"X-Arc-Session": token}
                ).status_code,
                401,
            )

    def test_sessions_are_isolated(self):
        self.assertEqual(
            resolve_session_actor(self.token, None),
            resolve_session_actor(self.token, None),
        )
        self.assertNotEqual(
            resolve_session_actor(self.token, None),
            resolve_session_actor(str(uuid.uuid4()), None),
        )

    def test_private_server_requires_key(self):
        with patch.dict(os.environ, {"ARC_BACKEND_API_KEY": "k" * 32}):
            headers = {"X-Arc-Session": self.token}
            self.assertEqual(
                self.client.get("/company/catalog", headers=headers).status_code, 401
            )
            headers["X-Arc-API-Key"] = "k" * 32
            self.assertEqual(
                self.client.get("/company/catalog", headers=headers).status_code, 200
            )

    def test_invalid_key_configuration_fails_closed(self):
        with patch.dict(os.environ, {"ARC_BACKEND_API_KEY": "short"}):
            self.assertEqual(
                self.client.get(
                    "/company/catalog", headers={"X-Arc-Session": self.token}
                ).status_code,
                503,
            )


class MemoryTests(unittest.TestCase):
    def test_new_instance_is_empty_and_results_are_copies(self):
        store = AgentStore()
        messages = [{"role": "user", "content": "hello"}]
        store.save_session("a", "ceo", "s", messages)
        messages[0]["content"] = "changed"
        result = store.load_session("a", "ceo", "s")
        self.assertEqual(result[0]["content"], "hello")
        result.clear()
        self.assertTrue(store.load_session("a", "ceo", "s"))
        self.assertIsNone(store.load_session("b", "ceo", "s"))
        self.assertIsNone(AgentStore().load_session("a", "ceo", "s"))

    def test_permission_is_consumed_atomically(self):
        store = AgentStore()
        store.set_permission("a", "it", "s", "tool", "allow", {}, time.time() + 60, 1)
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(
                executor.map(
                    lambda _: store.consume_permission("a", "it", "s", "tool"),
                    range(20),
                )
            )
        self.assertEqual(sum(item is not None for item in results), 1)

    def test_approval_is_single_use_and_expires(self):
        store = AgentStore()
        store.create_pending_action(
            {"approval_id": "one", "expires_at": time.time() + 60}
        )
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(
                executor.map(
                    lambda _: store.resolve_pending_action("one", "approved"), range(20)
                )
            )
        self.assertEqual(sum(results), 1)
        store.create_pending_action(
            {"approval_id": "old", "expires_at": time.time() - 1}
        )
        self.assertIsNone(store.get_pending_action("old"))
        self.assertFalse(store.resolve_pending_action("old", "approved"))
