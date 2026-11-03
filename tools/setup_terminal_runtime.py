"""Install ARC's private Linux container runtime from verified official sources.

This prepares a container engine only; it does not enable tools or execute
agent-supplied code. It never mounts the ARC source tree into a container.
"""

from __future__ import annotations

import hashlib
import io
import re
import subprocess
import tarfile
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / ".arc" / "terminal-runtime"
DISTRO = "ARC-Terminal"
SOURCE = "https://dl-cdn.alpinelinux.org/alpine/latest-stable/releases/x86_64/"


def run(*args: str, timeout: int = 120) -> str:
    result = subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    raw = result.stdout
    output = raw.decode(
        "utf-16le" if b"\0" in raw else "utf-8", errors="replace"
    ).strip()
    if output:
        print(output, flush=True)
    if result.returncode:
        raise RuntimeError(f"{args[0]} exited with code {result.returncode}")
    return output


def main() -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    with urlopen(SOURCE, timeout=30) as response:
        index = response.read(1_000_000).decode()
    releases = set(
        re.findall(r"alpine-minirootfs-(\d+\.\d+\.\d+)-x86_64\.tar\.gz", index)
    )
    if not releases:
        raise RuntimeError(
            "No stable Alpine root filesystem found at the official mirror"
        )
    version = max(releases, key=lambda value: tuple(map(int, value.split("."))))
    name = f"alpine-minirootfs-{version}-x86_64.tar.gz"
    archive = STATE / name
    with urlopen(SOURCE + name + ".sha256", timeout=30) as response:
        expected = response.read(1024).decode().split()[0].lower()
    if not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise RuntimeError("Invalid official SHA-256 checksum")
    if (
        not archive.exists()
        or hashlib.sha256(archive.read_bytes()).hexdigest() != expected
    ):
        with urlopen(SOURCE + name, timeout=60) as response:
            data = response.read(30_000_001)
        if len(data) > 30_000_000 or hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError("Root filesystem checksum or size validation failed")
        archive.write_bytes(data)
    print(f"Verified official Alpine {version} root filesystem.", flush=True)
    prepared = STATE / "arc-rootfs.tar"
    config = b"[automount]\nenabled=false\nmountFsTab=false\n[interop]\nenabled=false\nappendWindowsPath=false\n"
    with (
        tarfile.open(archive, "r:gz") as original,
        tarfile.open(prepared, "w") as target,
    ):
        for member in original:
            if member.name.lstrip("./") == "etc/wsl.conf":
                continue
            target.addfile(
                member, original.extractfile(member) if member.isfile() else None
            )
        member = tarfile.TarInfo("etc/wsl.conf")
        member.size = len(config)
        member.mode = 0o644
        target.addfile(member, io.BytesIO(config))
    existing = subprocess.run(
        ["wsl.exe", "--list", "--quiet"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    names = existing.stdout.decode(
        "utf-16le" if b"\0" in existing.stdout else "utf-8", errors="replace"
    )
    if DISTRO not in names.split():
        run(
            "wsl.exe",
            "--import",
            DISTRO,
            str(STATE / "distribution"),
            str(prepared),
            "--version",
            "2",
            timeout=120,
        )
    run(
        "wsl.exe",
        "-d",
        DISTRO,
        "-u",
        "root",
        "--exec",
        "/usr/bin/env",
        "-i",
        "PATH=/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME=/root",
        "/sbin/apk",
        "add",
        "--no-cache",
        "docker-engine",
        "docker-cli",
        "docker-cli-buildx",
        "ca-certificates",
        timeout=180,
    )
    print(
        "Container runtime installed. No agent tool permissions have been changed.",
        flush=True,
    )


if __name__ == "__main__":
    main()
