"""Prepare a fresh one-time code without rebuilding the local terminal."""

import hashlib
import json
import secrets
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    state = ROOT / ".arc/terminal-runtime"
    settings = json.loads((state / "gateway.json").read_text(encoding="utf-8"))
    path = Path(settings["grants_file"])
    grants = json.loads(path.read_text(encoding="utf-8"))
    code = secrets.token_urlsafe(32)
    grants.update(
        paired=False,
        pairing_hash=hashlib.sha256(code.encode()).hexdigest(),
        expires_at=time.time() + 3600,
    )
    temporary = path.with_suffix(".new")
    temporary.write_text(json.dumps(grants), encoding="utf-8")
    temporary.replace(path)
    (state / "pairing.json").write_text(json.dumps({"code": code}), encoding="utf-8")
    print(
        "A fresh one-time connection code is ready in the private terminal setup folder."
    )


if __name__ == "__main__":
    main()
