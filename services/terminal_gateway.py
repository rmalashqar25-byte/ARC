"""Loopback-only authenticated gateway to disposable, networkless containers."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib/backend"))
from fastapi import FastAPI, HTTPException, Request
from terminal_policy import validate_terminal_argv

CONFIG_PATH = Path(
    os.getenv("ARC_TERMINAL_GATEWAY_CONFIG", "")
    or ROOT / ".arc/terminal-runtime/gateway.json"
)
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
_gate = asyncio.Semaphore(1)


def config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def docker_command(configured, *args):
    if configured.get("engine") == "linux":
        if sys.platform != "linux":
            raise RuntimeError("The Linux terminal requires a Linux server")
        # Fixed executable and clean environment; never accept a shell command.
        return ["/usr/bin/docker", *args]
    if configured.get("engine", "wsl") != "wsl":
        raise ValueError("Unsupported terminal engine")
    executable = str(
        Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32" / "wsl.exe"
    )
    return [
        executable,
        "-d",
        configured["distribution"],
        "-u",
        "root",
        "--cd",
        "/",
        "--exec",
        "/usr/bin/env",
        "-i",
        "PATH=/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME=/root",
        "/usr/bin/docker",
        *args,
    ]


def host_environment():
    return {
        key: os.environ[key]
        for key in (
            "SYSTEMROOT",
            "WINDIR",
            "USERPROFILE",
            "LOCALAPPDATA",
            "TEMP",
            "TMP",
            "PATH",
        )
        if key in os.environ
    }


def authenticated(request):
    settings = config()
    expected = "Bearer " + settings["token"]
    supplied = request.headers.get("authorization", "")
    if not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(401, "A valid service connection is required")
    return settings


def validate_request(body, settings):
    if not isinstance(body, dict) or body.get("operation") != "run":
        raise ValueError("Unsupported terminal operation")
    actor = body.get("actor_id", "")
    grants = json.loads(Path(settings["grants_file"]).read_text(encoding="utf-8"))
    if not isinstance(actor, str) or actor not in grants.get("actors", []):
        raise PermissionError("Workspace is not connected to this terminal")
    workspace = body.get("workspace_id", "")
    prefix = hashlib.sha256(actor.encode()).hexdigest()[:24] + "/"
    if (
        not isinstance(workspace, str)
        or not re.fullmatch(r"[a-f0-9]{24}/[a-f0-9]{24}", workspace)
        or not workspace.startswith(prefix)
    ):
        raise ValueError("Invalid workspace identity")
    params = body.get("parameters", {})
    if not isinstance(params, dict):
        raise ValueError("Invalid terminal parameters")
    argv = validate_terminal_argv(params.get("argv"))
    executable = argv[0].lower().removesuffix(".exe")
    if executable not in {"git", "rg", "python", "python3", "pytest", "py"}:
        raise ValueError("Available commands are git, rg, Python and pytest")
    argv[0] = "python3" if executable in {"python", "python3", "py"} else executable
    return {
        "argv": argv,
        "cwd": params.get("cwd", "."),
        "files": params.get("files", {}),
        "timeout_seconds": min(max(int(params.get("timeout_seconds", 30)), 1), 120),
    }


def run_container(settings, job):
    name = "arc-job-" + uuid.uuid4().hex
    command = docker_command(
        settings,
        "run",
        "--rm",
        "--name",
        name,
        "-i",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges=true",
        "--pids-limit",
        "64",
        "--memory",
        "256m",
        "--memory-swap",
        "256m",
        "--cpus",
        "1",
        "--ulimit",
        "nofile=128:128",
        "--ulimit",
        "fsize=16777216:16777216",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,noexec,size=32m,uid=65534,gid=65534",
        "--tmpfs",
        "/workspace:rw,nosuid,nodev,size=16m,uid=65534,gid=65534",
        "--user",
        "65534:65534",
        "--workdir",
        "/workspace",
        settings["image_id"],
    )
    raw = json.dumps(job, ensure_ascii=True).encode()
    if len(raw) > 900_000:
        raise ValueError("Project snapshot is too large")
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=host_environment(),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    buffers = [bytearray(), bytearray()]
    overflow = threading.Event()

    def read(pipe, buffer):
        while True:
            chunk = pipe.read(4096)
            if not chunk:
                break
            remaining = 70_000 - len(buffer)
            buffer.extend(chunk[: max(remaining, 0)])
            if len(chunk) > remaining:
                overflow.set()
                break

    readers = [
        threading.Thread(target=read, args=(pipe, buffer), daemon=True)
        for pipe, buffer in zip((process.stdout, process.stderr), buffers)
    ]
    for reader in readers:
        reader.start()
    deadline = time.monotonic() + job["timeout_seconds"] + 15
    try:
        process.stdin.write(raw)
        process.stdin.close()
        while (
            process.poll() is None
            and not overflow.is_set()
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)
        interrupted = process.poll() is None or overflow.is_set()
        if interrupted:
            subprocess.run(
                docker_command(settings, "rm", "-f", name),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=host_environment(),
                timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            process.kill()
        process.wait(timeout=5)
        for reader in readers:
            reader.join(timeout=2)
        if interrupted:
            return {
                "exit_code": -1,
                "timed_out": not overflow.is_set(),
                "truncated": overflow.is_set(),
                "output": "Command stopped at its execution limit.",
            }
        if process.returncode:
            raise RuntimeError("The isolated terminal could not start this command")
        return json.loads(buffers[0])
    finally:
        if process.poll() is None:
            process.kill()
        subprocess.run(
            docker_command(settings, "rm", "-f", name),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=host_environment(),
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )


@app.get("/health")
async def health(request: Request):
    settings = authenticated(request)
    try:
        probe = await asyncio.to_thread(
            subprocess.run,
            docker_command(settings, "image", "inspect", settings["image_id"]),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=host_environment(),
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return {
            "ready": probe.returncode == 0,
            "commands": ["git", "rg", "python3", "pytest"],
        }
    except (OSError, subprocess.SubprocessError):
        return {"ready": False}


@app.post("/run")
async def terminal_run(request: Request):
    settings = authenticated(request)
    data = bytearray()
    async for part in request.stream():
        data.extend(part)
        if len(data) > 950_000:
            raise HTTPException(413, "Project snapshot is too large")
    try:
        job = validate_request(json.loads(data), settings)
    except PermissionError:
        raise HTTPException(403, "This workspace is not connected") from None
    except (ValueError, OSError, TypeError):
        raise HTTPException(400, "Invalid terminal request") from None
    if _gate.locked():
        raise HTTPException(429, "The terminal is busy; try again shortly")
    async with _gate:
        try:
            return await asyncio.to_thread(run_container, settings, job)
        except (ValueError, OSError, RuntimeError, subprocess.SubprocessError):
            raise HTTPException(
                503, "The terminal could not complete this command"
            ) from None


if __name__ == "__main__":
    clean_environment = host_environment()
    os.environ.clear()
    os.environ.update(clean_environment)
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8768)
    args = parser.parse_args()
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)
