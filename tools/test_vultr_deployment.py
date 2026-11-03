"""Release privacy and platform boundary regressions for the Vultr deployment."""

import importlib.util
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import package_vultr

spec = importlib.util.spec_from_file_location(
    "arc_deployment_gateway", package_vultr.ROOT / "services/terminal_gateway.py"
)
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)


class GatewayPlatformTests(unittest.TestCase):
    def test_linux_uses_fixed_executable_without_shell(self):
        with patch.object(gateway.sys, "platform", "linux"):
            self.assertEqual(
                gateway.docker_command(
                    {"engine": "linux"}, "image", "inspect", "sha256:abc"
                ),
                ["/usr/bin/docker", "image", "inspect", "sha256:abc"],
            )
        with patch.object(gateway.sys, "platform", "win32"):
            with self.assertRaises(RuntimeError):
                gateway.docker_command({"engine": "linux"}, "run")
        with self.assertRaises(ValueError):
            gateway.docker_command({"engine": "shell"}, "run")

    def test_provider_credentials_never_reach_docker_process(self):
        with patch.dict(
            os.environ,
            {
                "OPENROUTER_API_KEY": "private-test-value",
                "GEMINI_API_KEY": "private-test-value",
            },
        ):
            child = gateway.host_environment()
            self.assertNotIn("OPENROUTER_API_KEY", child)
            self.assertNotIn("GEMINI_API_KEY", child)


class ReleasePrivacyTests(unittest.TestCase):
    def prepare(self, root):
        for name in (
            "lib/backend/company/__init__.py",
            "lib/backend/app.py",
            "lib/backend/requirements.lock",
            "lib/backend/Dockerfile",
            "lib/backend/.dockerignore",
            "services/terminal_gateway.py",
            "services/terminal/runner.py",
            "deploy/vultr/install.sh",
            "compiled/index.html",
            "compiled/main.dart.js",
        ):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("release source\n", encoding="utf-8")

    def test_local_keys_and_database_are_excluded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.prepare(root)
            for name in (
                ".env",
                ".arc/provider-vault/vault.key",
                "lib/backend/test_private.py",
                "lib/backend/company/local.sqlite3",
            ):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("private-test-data", encoding="utf-8")
            output = root / "release.tar.gz"
            with patch.object(package_vultr, "ROOT", root):
                package_vultr.package(root / "compiled", output)
            with tarfile.open(output) as archive:
                names = archive.getnames()
                self.assertIn("web-build/main.dart.js", names)
                self.assertIn("release-manifest.json", names)
                self.assertNotIn(".env", names)
                self.assertFalse(
                    any(
                        "vault.key" in name
                        or name.endswith(".sqlite3")
                        or "test_private" in name
                        for name in names
                    )
                )

    def test_unexpected_secret_file_in_web_build_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.prepare(root)
            (root / "compiled/.env").write_text("private", encoding="utf-8")
            output = root / "release.tar.gz"
            with patch.object(package_vultr, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "Unsafe release path"):
                    package_vultr.package(root / "compiled", output)
            self.assertFalse(output.exists())
            self.assertFalse(output.with_suffix(".partial").exists())


if __name__ == "__main__":
    unittest.main()
