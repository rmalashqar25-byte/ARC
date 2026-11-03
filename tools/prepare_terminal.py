"""Build the local terminal image and prepare a one-time workspace connection."""

import hashlib
import io
import json
import secrets
import subprocess
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / ".arc/terminal-runtime"
DISTRO = "ARC-Terminal"
from dotenv import set_key


def command(*args):
    return [
        "wsl.exe",
        "-d",
        DISTRO,
        "-u",
        "root",
        "--cd",
        "/",
        "--exec",
        "/usr/bin/env",
        "-i",
        "PATH=/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME=/root",
        *args,
    ]


def run(*args, **kwargs):
    return subprocess.run(
        command(*args),
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        **kwargs,
    )


def main():
    STATE.mkdir(parents=True, exist_ok=True)
    for _ in range(12):
        try:
            probe = subprocess.run(
                command("/usr/bin/docker", "info"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=8,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if probe.returncode == 0:
                break
        except subprocess.TimeoutExpired:
            pass
        time.sleep(0.5)
    else:
        raise RuntimeError(
            "Start the ARC container engine before preparing the terminal"
        )
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name in ("Dockerfile", "runner.py"):
            source = ROOT / "services/terminal" / name
            data = source.read_bytes()
            member = tarfile.TarInfo(name)
            member.size = len(data)
            member.mode = 0o644
            archive.addfile(member, io.BytesIO(data))
    run(
        "/usr/bin/docker",
        "build",
        "--network=host",
        "-t",
        "arc-terminal:local",
        "-",
        input=buffer.getvalue(),
        timeout=240,
    )
    image = (
        run(
            "/usr/bin/docker",
            "image",
            "inspect",
            "arc-terminal:local",
            "--format",
            "{{.Id}}",
            stdout=subprocess.PIPE,
        )
        .stdout.decode()
        .strip()
    )
    if not image.startswith("sha256:"):
        raise RuntimeError("The terminal image was not verified")
    config_path = STATE / "gateway.json"
    settings = json.loads(config_path.read_text()) if config_path.exists() else {}
    token = settings.get("token") or secrets.token_urlsafe(48)
    pairing_code = secrets.token_urlsafe(32)
    grants = STATE / "grants.json"
    grants.write_text(
        json.dumps(
            {
                "actors": [],
                "paired": False,
                "pairing_hash": hashlib.sha256(pairing_code.encode()).hexdigest(),
                "expires_at": time.time() + 3600,
            }
        ),
        encoding="utf-8",
    )
    config_path.write_text(
        json.dumps(
            {
                "distribution": DISTRO,
                "image_id": image,
                "token": token,
                "grants_file": str(grants),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (STATE / "pairing.json").write_text(
        json.dumps({"code": pairing_code}), encoding="utf-8"
    )
    for name, value in {
        "ARC_TERMINAL_RUNNER_URL": "http://127.0.0.1:8768/run",
        "ARC_TERMINAL_RUNNER_TOKEN": token,
        "ARC_TERMINAL_GRANTS_FILE": str(grants),
    }.items():
        set_key(ROOT / ".env", name, value)
    print(
        "Local terminal image is ready. One-time workspace pairing is prepared; no cloud resources were created.",
        flush=True,
    )


if __name__ == "__main__":
    main()
