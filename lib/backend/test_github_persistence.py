"""GitHub installation metadata survives restarts without restoring transient access."""

import tempfile
import time
import unittest
from pathlib import Path

from agent_store import AgentStore
from company.work_store import WorkStore


class GitHubPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = WorkStore(Path(self.temporary.name) / "company.sqlite3")
        self.store = self.reopen()

    def reopen(self):
        store = AgentStore()
        store.bind_work_store(self.database)
        return store

    def connect(self, actor, installation):
        self.store.save_github_connection(
            actor_id=actor,
            installation_id=installation,
            account_login="example-owner",
            account_type="User",
            github_user_id="123",
            github_user_login="example-user",
        )

    def test_restart_preserves_only_the_owning_workspaces_metadata(self):
        self.connect("owner", 10)
        self.connect("other", 20)
        expected = self.store.list_github_connections("owner")
        self.store.create_github_oauth_state("x" * 64, "owner", time.time() + 60)
        recovered = self.reopen()
        self.assertEqual(recovered.list_github_connections("owner"), expected)
        self.assertEqual(recovered.list_github_connections("unknown"), [])
        self.assertEqual(
            recovered.list_github_connections("other")[0]["installation_id"], 20
        )
        self.assertIsNone(recovered.consume_github_oauth_state("x" * 64))
        self.assertNotIn("access_token", expected[0])

    def test_revocation_is_scoped_and_survives_restart(self):
        self.connect("owner", 10)
        self.assertFalse(self.store.delete_github_connection("other", 10))
        self.assertTrue(self.store.delete_github_connection("owner", 10))
        self.assertEqual(self.reopen().list_github_connections("owner"), [])

    def test_existing_database_without_github_metadata_still_opens(self):
        snapshot = self.store.company_snapshot()
        snapshot.pop("github_connections")
        self.database.save_state(snapshot)
        self.assertEqual(self.reopen().list_github_connections("owner"), [])


if __name__ == "__main__":
    unittest.main()
