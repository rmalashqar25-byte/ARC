"""Check tracked and new source files without printing credential values."""

import argparse
import re
import subprocess
import sys
from pathlib import Path

PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "provider credential": re.compile(
        r"(?:sk-or-v1-[a-zA-Z0-9]{40,}|AIza[0-9A-Za-z_-]{35}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})"
    ),
}


def findings(root, *, staged=False):
    args = ["git", "ls-files", "--cached", "-z"]
    if not staged:
        args.extend(["--others", "--exclude-standard"])
    files = subprocess.check_output(args, cwd=root).decode("utf-8").split("\0")
    for name in sorted(set(filter(None, files))):
        path = root / name
        parts = path.relative_to(root).parts
        if (
            any(part in {".venv", "venv", "__pycache__", ".arc"} for part in parts)
            or path.suffix == ".pyc"
        ):
            yield name, 0, "tracked runtime artifact"
            continue
        if "secrets" in path.relative_to(root).parts or (
            path.name.startswith(".env") and path.name != ".env.example"
        ):
            yield name, 0, "tracked secret file"
            continue
        if staged:
            raw = subprocess.check_output(["git", "show", f":{name}"], cwd=root)
        else:
            if not path.is_file() or path.is_symlink():
                continue
            raw = path.read_bytes()
        if b"\0" in raw[:8192]:
            continue
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeError:
            continue
        for kind, pattern in PATTERNS.items():
            for match in pattern.finditer(content):
                yield name, content[: match.start()].count("\n") + 1, kind


def check(root=None, *, staged=False):
    root = root or Path(__file__).resolve().parent.parent
    results = list(findings(root, staged=staged))
    for name, line, kind in results:
        print(f"{name}:{line}: {kind} detected; value withheld")
    print(f"Source credential check: {len(results)} findings")
    return bool(results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--staged", action="store_true", help="Inspect exact Git index contents"
    )
    options = parser.parse_args()
    sys.exit(check(staged=options.staged))
