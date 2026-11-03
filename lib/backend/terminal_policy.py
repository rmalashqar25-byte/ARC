"""Shared command validation for the API and isolated terminal gateway."""

import re
from pathlib import Path
from typing import Any

SENSITIVE_PATH_MARKERS = {
    "client_secret",
    "credential",
    "credentials",
    "keystore",
    "private_key",
    "secret",
    ".aws",
    ".ssh",
    ".azure",
    ".codex",
    ".agents",
    ".github",
}


def validate_terminal_argv(argv: Any) -> list[str]:
    if not isinstance(argv, list) or not argv or len(argv) > 24:
        raise ValueError("argv must be a non-empty list with at most 24 items")
    cleaned = [str(item) for item in argv]
    if any(not item or "\x00" in item or len(item) > 500 for item in cleaned):
        raise ValueError("Terminal arguments contain an invalid value")
    if not re.fullmatch(r"[A-Za-z0-9]+(?:\.exe)?", cleaned[0]):
        raise ValueError("Executable paths are not allowed")
    executable = cleaned[0].lower().removesuffix(".exe")
    allowed_commands = {
        "git",
        "rg",
        "flutter",
        "dart",
        "pytest",
        "python",
        "python3",
        "py",
    }
    if executable not in allowed_commands:
        raise ValueError(f"Command '{executable}' is not in the terminal allowlist")

    subcommand = cleaned[1].lower() if len(cleaned) > 1 else ""
    if executable == "git" and subcommand not in {
        "status",
        "diff",
        "log",
        "show",
        "branch",
        "rev-parse",
        "ls-files",
        "grep",
    }:
        raise ValueError("Only read-only git commands are allowed")
    if executable in {"flutter", "dart"} and subcommand not in {"analyze", "test"}:
        raise ValueError(f"Only {executable} analyze and {executable} test are allowed")
    if executable in {"python", "python3", "py"} and cleaned[1:3] != ["-m", "pytest"]:
        raise ValueError("Python is allowed only as: python -m pytest")

    dangerous_options = {
        "--config",
        "--ext-diff",
        "--hidden",
        "--no-ignore",
        "--no-index",
        "--output",
        "--pre",
        "--pre-glob",
        "--textconv",
        "-o",
    }
    option_names = {
        item.lower().split("=", 1)[0] for item in cleaned[1:] if item.startswith("-")
    }
    if option_names & dangerous_options or any(
        re.fullmatch(r"-u+", item) for item in cleaned[1:]
    ):
        raise ValueError(
            "A terminal option that can execute helpers, bypass ignore rules, or write files is blocked"
        )

    if executable == "git" and subcommand == "branch":
        safe_branch_options = {
            "--list",
            "-a",
            "--all",
            "-r",
            "--remotes",
            "--show-current",
        }
        branch_options = {item.lower() for item in cleaned[2:] if item.startswith("-")}
        if branch_options - safe_branch_options:
            raise ValueError("Only read-only git branch options are allowed")
        if any(not item.startswith("-") for item in cleaned[2:]):
            raise ValueError("git branch cannot create, rename, or delete branches")

    lowered = [item.lower() for item in cleaned[1:]]
    if any(
        Path(item).is_absolute() or ".." in Path(item).parts
        for item in cleaned[1:]
        if not item.startswith("-")
    ):
        raise ValueError("Terminal paths must stay relative to the workspace")
    if any(
        item == ".env"
        or item.endswith((".pem", ".key", ".p12", ".pfx", ".jks", ".keystore"))
        or any(marker in item for marker in SENSITIVE_PATH_MARKERS)
        for item in lowered
    ):
        raise ValueError("Terminal access to secret-bearing files is blocked")
    return cleaned
