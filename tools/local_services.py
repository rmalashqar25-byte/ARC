"""Keep an already installed ARC terminal available for the local launcher."""

import json
import os
import re
import socket
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_lock = threading.Lock()


def listening(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def ensure_terminal():
    state = ROOT / ".arc/terminal-runtime"
    config = state / "gateway.json"
    if os.name != "nt" or not config.is_file():
        return
    with _lock:
        settings = json.loads(config.read_text(encoding="utf-8"))
        if settings.get("distribution") != "ARC-Terminal" or not re.fullmatch(
            r"sha256:[a-f0-9]{64}", settings.get("image_id", "")
        ):
            return
        # Child processes do not receive model, GitHub, or cloud credentials.
        env = {
            k: v
            for k, v in os.environ.items()
            if k.upper()
            in {
                "SYSTEMROOT",
                "WINDIR",
                "PATH",
                "TEMP",
                "TMP",
                "USERPROFILE",
                "LOCALAPPDATA",
                "APPDATA",
                "PYTHONPATH",
            }
        }
        wsl = str(Path(env.get("SYSTEMROOT", "C:/Windows")) / "System32/wsl.exe")
        command = [
            wsl,
            "-d",
            "ARC-Terminal",
            "-u",
            "root",
            "--cd",
            "/",
            "--exec",
            "/usr/bin/env",
            "-i",
            "PATH=/usr/sbin:/usr/bin:/sbin:/bin",
            "HOME=/root",
        ]
        try:
            ready = (
                subprocess.run(
                    [
                        *command,
                        "/usr/bin/docker",
                        "image",
                        "inspect",
                        settings["image_id"],
                    ],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=8,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    check=False,
                ).returncode
                == 0
            )
        except (OSError, subprocess.TimeoutExpired):
            ready = False
        if not ready:
            with (
                (state / "engine-out.log").open("a", encoding="utf-8") as out,
                (state / "engine-error.log").open("a", encoding="utf-8") as err,
            ):
                subprocess.Popen(
                    [
                        *command,
                        "/usr/bin/dockerd",
                        "--bridge=none",
                        "--iptables=false",
                        "--ip-forward=false",
                        "--ip-masq=false",
                    ],
                    env=env,
                    stdout=out,
                    stderr=err,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
        if not listening(8768):
            with (
                (state / "gateway-out.log").open("a", encoding="utf-8") as out,
                (state / "gateway-error.log").open("a", encoding="utf-8") as err,
            ):
                subprocess.Popen(
                    [sys.executable, str(ROOT / "services/terminal_gateway.py")],
                    cwd=ROOT,
                    env=env,
                    stdout=out,
                    stderr=err,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )


def supervise(stop):
    while not stop.is_set():
        try:
            ensure_terminal()
        except (OSError, ValueError):
            pass
        stop.wait(30)


if __name__ == "__main__":
    ensure_terminal()
    print("Checked the configured local terminal services.")
