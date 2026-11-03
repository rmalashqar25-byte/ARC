"""Verify backend-to-terminal transport with a synthetic private project."""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib/backend"))
from agent_tools import ToolContext, _terminal_run


async def main():
    settings = json.loads((ROOT / ".arc/terminal-runtime/gateway.json").read_text())
    grants = json.loads(Path(settings["grants_file"]).read_text())
    actor = grants["actors"][0]
    os.environ["ARC_TERMINAL_RUNNER_URL"] = "http://127.0.0.1:8768/run"
    os.environ["ARC_TERMINAL_RUNNER_TOKEN"] = settings["token"]
    os.environ["ARC_TERMINAL_GRANTS_FILE"] = settings["grants_file"]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "test_arc.py").write_text("def test_arc():\n    assert 6 * 7 == 42\n")
        result = await _terminal_run(
            {"argv": ["python", "-m", "pytest", "-q"]},
            ToolContext("it", "terminal-connection-check", actor, root),
        )
    command = result.get("result", {})
    if (
        result.get("status") != "completed"
        or command.get("exit_code") != 0
        or "1 passed" not in command.get("output", "")
    ):
        raise RuntimeError(
            "Backend-to-terminal verification failed: " + json.dumps(result)
        )
    report_path = ROOT / ".arc/terminal-runtime/verification.json"
    report = json.loads(report_path.read_text())
    report["backend_to_gateway_test"] = "passed"
    report_path.write_text(json.dumps(report, indent=2))
    print(
        "Verified a real private-project pytest command through the ARC backend transport."
    )


if __name__ == "__main__":
    asyncio.run(main())
