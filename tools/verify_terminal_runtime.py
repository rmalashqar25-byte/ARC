"""Exercise the actual local container using only synthetic test projects."""

import base64
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services"))
from terminal_gateway import config, run_container


def encoded(source):
    return base64.b64encode(source.encode()).decode()


def main():
    settings = config()
    source = """import os, pathlib, socket, pytest
def test_identity_and_environment():
    assert os.getuid() == 65534
    assert 'OPENROUTER_API_KEY' not in os.environ
    assert 'GITHUB_CLIENT_SECRET' not in os.environ
    assert not pathlib.Path('/mnt/c').exists()
    assert not pathlib.Path('/var/run/docker.sock').exists()
def test_readonly_system():
    with pytest.raises(OSError):
        pathlib.Path('/etc/arc-host-write').write_text('denied')
def test_network_is_disabled():
    with socket.socket() as connection:
        connection.settimeout(1)
        with pytest.raises(OSError):
            connection.connect(('1.1.1.1',443))
def test_limits_and_capabilities():
    assert int(pathlib.Path('/sys/fs/cgroup/memory.max').read_text()) <= 268435456
    assert int(pathlib.Path('/sys/fs/cgroup/pids.max').read_text()) <= 64
    status = pathlib.Path('/proc/self/status').read_text()
    assert 'CapEff:\\t0000000000000000' in status
"""
    result = run_container(
        settings,
        {
            "argv": ["python3", "-m", "pytest", "-q"],
            "cwd": ".",
            "files": {"test_isolation.py": encoded(source)},
            "timeout_seconds": 15,
        },
    )
    if result.get("exit_code") != 0 or "4 passed" not in result.get("output", ""):
        raise RuntimeError("Container isolation checks failed: " + json.dumps(result))
    print("Passed 4 real container isolation checks.", flush=True)
    started = time.monotonic()
    timed = run_container(
        settings,
        {
            "argv": ["python3", "-m", "pytest", "-q"],
            "cwd": ".",
            "files": {
                "test_timeout.py": encoded(
                    "import time\ndef test_wait(): time.sleep(60)\n"
                )
            },
            "timeout_seconds": 1,
        },
    )
    if not timed.get("timed_out") or time.monotonic() - started > 20:
        raise RuntimeError("Container time limit did not stop the command")
    print("Passed real command timeout and cleanup check.", flush=True)
    report = {
        "isolation_tests": 4,
        "timeout_test": "passed",
        "engine": settings.get("engine", "wsl"),
    }
    destination = Path(
        os.getenv("ARC_TERMINAL_VERIFICATION_REPORT", "")
        or ROOT / ".arc/terminal-runtime/verification.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
