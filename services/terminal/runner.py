"""One disposable project command. No credentials, host mounts, or network."""

import base64
import json
import os
import resource
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath

MAX_INPUT = 900_000
MAX_FILES = 200
MAX_FILE_BYTES = 512_000
MAX_OUTPUT = 60_000


def relative(value):
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
        raise ValueError("Invalid project path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or len(value) > 240:
        raise ValueError("Project path is outside its workspace")
    if any(part.startswith(".") or ":" in part for part in path.parts):
        raise ValueError("Hidden or special project paths are not accepted")
    return path


def run_job(job):
    files = job.get("files", {})
    if not isinstance(files, dict) or len(files) > MAX_FILES:
        raise ValueError("Project snapshot exceeds the file limit")
    total = 0
    root = Path("/workspace")
    for name, content in files.items():
        destination = root.joinpath(relative(name))
        data = base64.b64decode(content, validate=True)
        total += len(data)
        if total > MAX_FILE_BYTES:
            raise ValueError("Project snapshot exceeds the size limit")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    cwd = job.get("cwd", ".")
    directory = root if cwd == "." else root.joinpath(relative(cwd))
    if not directory.is_dir():
        raise ValueError("Project working directory does not exist")
    argv = job.get("argv")
    if (
        not isinstance(argv, list)
        or not argv
        or not all(isinstance(v, str) for v in argv)
    ):
        raise ValueError("Invalid command")
    if argv[0] not in {"git", "rg", "pytest", "python3", "python"}:
        raise ValueError("This command is not installed in the terminal")
    if argv[0] == "python":
        argv[0] = "python3"
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/tmp",
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
    }
    timeout = min(max(int(job.get("timeout_seconds", 30)), 1), 120)
    resource.setrlimit(resource.RLIMIT_CPU, (timeout + 1, timeout + 2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16_000_000, 16_000_000))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    if argv[0] == "git":
        subprocess.run(
            ["git", "init", "-q", str(root)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    process = subprocess.Popen(
        argv,
        cwd=directory,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    output = bytearray()
    timed_out = truncated = False
    deadline = time.monotonic() + timeout
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    while selector.get_map():
        if time.monotonic() >= deadline:
            timed_out = True
            break
        for key, _ in selector.select(timeout=0.1):
            chunk = os.read(key.fileobj.fileno(), 4096)
            if not chunk:
                selector.unregister(key.fileobj)
                break
            remaining = MAX_OUTPUT - len(output)
            output.extend(chunk[:remaining])
            if len(chunk) > remaining:
                truncated = True
                break
        if truncated:
            break
    if timed_out or truncated:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=2)
    selector.close()
    return {
        "exit_code": process.returncode,
        "output": output.decode("utf-8", errors="replace"),
        "timed_out": timed_out,
        "truncated": truncated,
        "files_received": len(files),
        "workspace_changes_saved": False,
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            raise ValueError("Project request is too large")
        result = run_job(json.loads(raw))
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        result = {"exit_code": 1, "error": str(error)[:500]}
    print(json.dumps(result, ensure_ascii=True))
