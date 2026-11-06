"""Package an allowlisted deployment without local keys, sessions, or runtime data."""

import argparse
import hashlib
import io
import json
import tarfile
from pathlib import Path

from check_source_secrets import PATTERNS

ROOT = Path(__file__).resolve().parent.parent


def release_files(web):
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md", "THIRD_PARTY_LICENSES.txt"):
        path = ROOT / name
        yield path, name
    backend = ROOT / "lib/backend"
    for path in sorted(backend.glob("*.py")):
        if not path.name.startswith("test_"):
            yield path, path.relative_to(ROOT).as_posix()
    for name in ("requirements.lock", "Dockerfile", ".dockerignore"):
        path = backend / name
        yield path, path.relative_to(ROOT).as_posix()
    for path in sorted((backend / "company").iterdir()):
        if (
            path.is_file()
            and path.suffix in {".py", ".json"}
            and not path.name.startswith("test_")
        ):
            yield path, path.relative_to(ROOT).as_posix()
    for directory in (ROOT / "deploy/vultr", ROOT / "services/terminal"):
        for path in sorted(directory.iterdir()):
            if path.is_file() and (
                path.suffix in {".py", ".sh", ".yaml", ".md", ".gateway"}
                or path.name in {"Dockerfile", "Caddyfile"}
            ):
                yield path, path.relative_to(ROOT).as_posix()
    path = ROOT / "services/terminal_gateway.py"
    yield path, path.relative_to(ROOT).as_posix()
    for path in sorted(web.rglob("*")):
        if path.is_file():
            yield path, "web-build/" + path.relative_to(web).as_posix()


def package(web, output):
    if not (web / "index.html").is_file() or not (web / "main.dart.js").is_file():
        raise ValueError("A complete Flutter release build is required")
    selected = list(release_files(web))
    manifest = {}
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".partial")
    try:
        with tarfile.open(temporary, "w:gz") as archive:
            for path, name in selected:
                if path.is_symlink() or any(
                    p in {"secrets", ".arc", ".env", "__pycache__", ".git"}
                    for p in Path(name).parts
                ):
                    raise ValueError("Unsafe release path: " + name)
                raw = path.read_bytes()
                if path.suffix in {
                    ".py",
                    ".sh",
                    ".yaml",
                    ".md",
                    ".gateway",
                } or path.name in {"Caddyfile", "Dockerfile", "requirements.lock"}:
                    raw = raw.replace(b"\r\n", b"\n")
                text = raw.decode("utf-8", errors="ignore")
                if any(pattern.search(text) for pattern in PATTERNS.values()):
                    raise ValueError("Credential pattern detected in " + name)
                info = tarfile.TarInfo(name)
                info.size = len(raw)
                info.mode = 0o755 if path.suffix == ".sh" else 0o644
                archive.addfile(info, io.BytesIO(raw))
                manifest[name] = hashlib.sha256(raw).hexdigest()
            raw = json.dumps(manifest, indent=2).encode()
            info = tarfile.TarInfo("release-manifest.json")
            info.size = len(raw)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(raw))
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    print(
        f"Release prepared: {len(manifest)} files, {output.stat().st_size:,} bytes. No local state included."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web-dir", type=Path, default=ROOT / ".arc/vultr/web")
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".arc/vultr/arc-release.tar.gz"
    )
    args = parser.parse_args()
    package(args.web_dir.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
