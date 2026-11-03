"""Credential checks cover new files and the exact staged contents."""

import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path

from check_source_secrets import check, findings


class SourceSecretsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        self.token = "gh" + "p_" + "a" * 40

    def git(self, *args):
        return subprocess.check_output(
            ["git", *args], cwd=self.root, stderr=subprocess.PIPE
        )

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_new_source_is_checked(self):
        self.write("new.py", self.token)
        self.assertEqual(
            list(findings(self.root)), [("new.py", 1, "provider credential")]
        )

    def test_ignored_configuration_stays_private(self):
        self.write(".gitignore", ".env\n")
        self.write(".env", self.token)
        self.assertEqual(list(findings(self.root)), [])

    def test_forced_tracked_secrets_and_runtime_are_rejected(self):
        self.write(".env", "safe-looking content")
        self.write(".venv/runtime.txt", "runtime")
        self.git("add", "-f", ".env", ".venv/runtime.txt")
        self.assertEqual(
            {row[2] for row in findings(self.root)},
            {"tracked secret file", "tracked runtime artifact"},
        )

    def test_index_is_checked_even_after_worktree_is_cleaned(self):
        self.write("code.py", self.token)
        self.git("add", "code.py")
        self.write("code.py", "clean")
        self.assertEqual(list(findings(self.root)), [])
        self.assertEqual(len(list(findings(self.root, staged=True))), 1)

    def test_large_source_is_not_silently_skipped(self):
        self.write("large.txt", "x" * 2_000_001 + "\n" + self.token)
        self.assertEqual(list(findings(self.root))[0][1], 2)

    def test_output_never_contains_the_secret(self):
        self.write("code.py", self.token)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertTrue(check(self.root))
        self.assertNotIn(self.token, output.getvalue())


if __name__ == "__main__":
    unittest.main()
