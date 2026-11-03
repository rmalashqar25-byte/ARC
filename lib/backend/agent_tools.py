import ast
import base64
import hashlib
import hmac
import inspect
import json
import logging
import math
import os
import re
import secrets
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import httpx
from agent_store import VALID_PERMISSION_MODES, get_agent_store
from terminal_connection import terminal_is_connected
from terminal_policy import validate_terminal_argv as _validate_terminal_argv

logger = logging.getLogger(__name__)

LOW_RISK = "low"
APPROVAL_REQUIRED = "approval_required"
WRITE_RISK = "write"
EXTERNAL_RISK = "external"
RECOVERABLE_DELETE_RISK = "recoverable_delete"
APPROVAL_TTL_SECONDS = 10 * 60
MAX_TOOL_OUTPUT_CHARS = 20_000
FILE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = FILE_DIR.parent.parent if FILE_DIR.name == "backend" else FILE_DIR
TEXT_FILE_SUFFIXES = {
    ".dart",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".md",
    ".txt",
    ".csv",
    ".html",
    ".css",
    ".kt",
    ".java",
    ".xml",
    ".gradle",
}
IGNORED_PATH_PARTS = {
    ".arc",
    ".git",
    ".dart_tool",
    ".venv",
    "build",
    "__pycache__",
    "node_modules",
}
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


@dataclass(frozen=True)
class ToolContext:
    role: str
    session_id: str
    actor_id: str = "local"
    workspace_root: Path = PROJECT_ROOT
    delegation_depth: int = 0
    company_group_id: str | None = None


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    risk: str | Callable[[dict[str, Any]], str]
    handler: Callable[[dict[str, Any], ToolContext], Any]

    def risk_for(self, arguments: dict[str, Any]) -> str:
        return self.risk(arguments) if callable(self.risk) else self.risk

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def _utc_iso(timestamp: float | None = None) -> str:
    value = time.time() if timestamp is None else timestamp
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _redact(value: Any, key: str = "") -> Any:
    sensitive = ("password", "secret", "token", "api_key", "authorization", "cookie")
    if any(part in key.lower() for part in sensitive):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            str(item_key): _redact(item, str(item_key))
            for item_key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str) and len(value) > 2_000:
        return value[:2_000] + "...[truncated]"
    return value


def _contains_secret_field(value: Any) -> bool:
    markers = (
        "password",
        "secret",
        "token",
        "api_key",
        "authorization",
        "cookie",
        "otp",
    )
    if isinstance(value, dict):
        for item_key, item_value in value.items():
            normalized_key = str(item_key).lower().replace("-", "_")
            if any(marker in normalized_key for marker in markers):
                return True
            if _contains_secret_field(item_value):
                return True
    elif isinstance(value, list):
        return any(_contains_secret_field(item) for item in value)
    return False


def _audit(event: str, context: ToolContext, tool_name: str, **details: Any) -> None:
    now = time.time()
    record = {
        "timestamp": _utc_iso(now),
        "timestamp_epoch": now,
        "event": event,
        "role": context.role,
        "session_id": context.session_id,
        "actor_id": context.actor_id,
        "tool": tool_name,
        "details": _redact(details),
    }
    from company.work_policy import WORK_SCOPE

    scope = WORK_SCOPE.get()
    if (
        scope
        and scope["actor"] == context.actor_id
        and scope["session"] == context.session_id
    ):
        record["work_task_id"] = scope.get("task_id")
    get_agent_store().append_audit(record)


def get_audit_events(
    session_id: str | None = None,
    limit: int = 100,
    actor_id: str | None = None,
) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit), 1), 500)
    if not actor_id:
        return []
    records = get_agent_store().get_audit(actor_id, session_id, safe_limit)
    for record in records:
        record["timestamp_iso"] = _utc_iso(float(record["timestamp"]))
    return records


def _workspace_root(actor_id: str = "local", session_id: str = "default") -> Path:
    configured = os.getenv("ARC_AGENT_WORKSPACE_ROOT", "").strip()
    root = (
        Path(configured).expanduser().resolve()
        if configured
        else PROJECT_ROOT.resolve()
    )
    if not root.is_dir():
        raise RuntimeError("ARC_AGENT_WORKSPACE_ROOT must be an existing directory")
    filesystem_root = Path(root.anchor).resolve()
    if root in {filesystem_root, Path.home().resolve()}:
        raise RuntimeError(
            "ARC_AGENT_WORKSPACE_ROOT cannot be a filesystem or home-directory root"
        )
    # The configured directory is a storage base, never a shared user workspace.
    relative = (
        Path(".arc")
        / "workspaces"
        / _actor_storage_key(actor_id)
        / _actor_storage_key(session_id)
    )
    if _has_symlink_component(root, str(relative)):
        raise ValueError("Workspace storage cannot contain links or junctions")
    workspace = _safe_path(root, str(relative))
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _validate_path_spelling(value: str) -> None:
    # Block Windows ADS, device names, drive-relative paths and trailing-dot aliases
    # on every OS so policy behaves the same after deployment.
    if "\x00" in value or ":" in value:
        raise ValueError("Unsupported workspace path spelling")
    for part in value.replace("\\", "/").split("/"):
        if part in {"", ".", ".."}:
            continue
        if part.endswith((".", " ")) or re.fullmatch(
            r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part
        ):
            raise ValueError("Reserved or ambiguous workspace path")


def _safe_path(root: Path, relative_path: str) -> Path:
    candidate_text = (relative_path or ".").strip()
    _validate_path_spelling(candidate_text)
    candidate = Path(candidate_text)
    if candidate.is_absolute():
        raise ValueError("Only paths relative to the configured workspace are allowed")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError("Path escapes the configured workspace")
    return resolved


def _has_symlink_component(root: Path, relative_path: str) -> bool:
    current = root.resolve()
    for part in Path(relative_path).parts:
        current = current / part
        if current.is_symlink() or (
            hasattr(current, "is_junction") and current.is_junction()
        ):
            return True
    return False


def _is_sensitive_path(path: Path) -> bool:
    _validate_path_spelling(path.as_posix())
    lowered_parts = [part.lower() for part in path.parts]
    name = path.name.lower()
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        return True
    if path.suffix.lower() in {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore"}:
        return True
    return any(
        marker in part for part in lowered_parts for marker in SENSITIVE_PATH_MARKERS
    )


def _calculate(arguments: dict[str, Any], _: ToolContext) -> dict[str, Any]:
    expression = str(arguments.get("expression", "")).strip()
    if not expression or len(expression) > 500:
        raise ValueError("expression must contain between 1 and 500 characters")
    tree = ast.parse(expression, mode="eval")

    binary_ops = {
        ast.Add: lambda left, right: left + right,
        ast.Sub: lambda left, right: left - right,
        ast.Mult: lambda left, right: left * right,
        ast.Div: lambda left, right: left / right,
        ast.FloorDiv: lambda left, right: left // right,
        ast.Mod: lambda left, right: left % right,
        ast.Pow: lambda left, right: left**right,
    }
    unary_ops = {ast.UAdd: lambda value: value, ast.USub: lambda value: -value}

    def evaluate(node: ast.AST) -> float | int:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in binary_ops:
            left = evaluate(node.left)
            right = evaluate(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ValueError("Exponent is too large")
            return binary_ops[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in unary_ops:
            return unary_ops[type(node.op)](evaluate(node.operand))
        raise ValueError("Only numeric arithmetic is allowed")

    original_evaluate = evaluate

    def evaluate(node: ast.AST) -> float | int:
        value = original_evaluate(node)
        try:
            if abs(value) > 1e100 or not math.isfinite(value):
                raise ValueError("Calculation intermediate exceeds the supported range")
        except OverflowError:
            raise ValueError(
                "Calculation intermediate exceeds the supported range"
            ) from None
        return value

    result = evaluate(tree)
    if not math.isfinite(float(result)) or abs(float(result)) > 1e100:
        raise ValueError("Calculation result is outside the supported range")
    return {"expression": expression, "result": result}


def _finance_summary(arguments: dict[str, Any], _: ToolContext) -> dict[str, Any]:
    transactions = arguments.get("transactions")
    if (
        not isinstance(transactions, list)
        or not transactions
        or len(transactions) > 2_000
    ):
        raise ValueError(
            "transactions must be a non-empty list with at most 2000 entries"
        )

    income = 0.0
    expenses = 0.0
    categories: dict[str, float] = {}
    for item in transactions:
        if not isinstance(item, dict):
            raise ValueError("Every transaction must be an object")
        kind = str(item.get("kind", "")).strip().lower()
        if kind not in {"income", "expense"}:
            raise ValueError("Transaction kind must be income or expense")
        amount = float(item.get("amount", 0))
        if not math.isfinite(amount) or amount < 0:
            raise ValueError("Transaction amounts must be finite and non-negative")
        category = (
            str(item.get("category", "uncategorized")).strip()[:100] or "uncategorized"
        )
        signed_amount = amount if kind == "income" else -amount
        categories[category] = categories.get(category, 0.0) + signed_amount
        if kind == "income":
            income += amount
        else:
            expenses += amount

    return {
        "income": round(income, 2),
        "expenses": round(expenses, 2),
        "net_cash_flow": round(income - expenses, 2),
        "category_net": {
            key: round(value, 2) for key, value in sorted(categories.items())
        },
        "transaction_count": len(transactions),
    }


def _workspace_search(
    arguments: dict[str, Any], context: ToolContext
) -> dict[str, Any]:
    query = str(arguments.get("query", "")).strip()
    if not query or len(query) > 200:
        raise ValueError("query must contain between 1 and 200 characters")
    location = str(arguments.get("path", "."))
    if _has_symlink_component(context.workspace_root, location):
        raise ValueError("Symbolic links cannot be searched by an agent")
    search_root = _safe_path(context.workspace_root, location)
    if not search_root.exists():
        raise ValueError("Search path does not exist")

    matches: list[dict[str, Any]] = []
    candidates = [search_root] if search_root.is_file() else search_root.rglob("*")
    for path in candidates:
        if len(matches) >= 50:
            break
        if (
            path.is_symlink()
            or not path.is_file()
            or path.suffix.lower() not in TEXT_FILE_SUFFIXES
        ):
            continue
        resolved_path = path.resolve()
        resolved_root = context.workspace_root.resolve()
        if (
            resolved_path != resolved_root
            and resolved_root not in resolved_path.parents
        ):
            continue
        relative = resolved_path.relative_to(resolved_root)
        if any(
            part.lower() in IGNORED_PATH_PARTS for part in relative.parts
        ) or _is_sensitive_path(relative):
            continue
        try:
            if path.stat().st_size > 1_000_000:
                continue
            for number, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if query.casefold() in line.casefold():
                    matches.append(
                        {"path": str(relative), "line": number, "text": line[:500]}
                    )
                    if len(matches) >= 50:
                        break
        except OSError:
            continue
    return {"query": query, "matches": matches, "truncated": len(matches) >= 50}


def _workspace_read(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    relative_path = str(arguments.get("path", "")).strip()
    if not relative_path:
        raise ValueError("path is required")
    if _has_symlink_component(context.workspace_root, relative_path):
        raise ValueError("Reading symbolic links is blocked")
    path = _safe_path(context.workspace_root, relative_path)
    if not path.is_file():
        raise ValueError("Requested path is not a file")
    relative = path.relative_to(context.workspace_root)
    if path.suffix.lower() not in TEXT_FILE_SUFFIXES:
        raise ValueError("Only supported text files can be read")
    if any(
        part.lower() in IGNORED_PATH_PARTS for part in relative.parts
    ) or _is_sensitive_path(relative):
        raise ValueError("Reading secret-bearing files is blocked")
    max_chars = min(max(int(arguments.get("max_chars", 12_000)), 1), 20_000)
    if path.stat().st_size > 1_000_000:
        raise ValueError("Files larger than 1 MB cannot be read by this tool")
    with path.open(encoding="utf-8", errors="replace") as source:
        content = source.read(1_000_001)
    return {
        "path": str(relative),
        "content": content[:max_chars],
        "truncated": len(content) > max_chars,
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
    }


def _private_storage(context: ToolContext, relative: Path) -> Path:
    if _has_symlink_component(context.workspace_root, str(relative)):
        raise ValueError("Private tool storage cannot contain links or junctions")
    return _safe_path(context.workspace_root, str(relative))


def _draft_file(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    raw_name = str(arguments.get("name", "draft.md")).strip()
    content = str(arguments.get("content", ""))
    if not content or len(content) > 100_000:
        raise ValueError("content must contain between 1 and 100000 characters")
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(raw_name).name).strip("._")
    if not safe_name:
        safe_name = "draft.md"
    draft_root = _private_storage(context, Path(".arc") / "drafts" / context.role)
    draft_root.mkdir(parents=True, exist_ok=True)
    destination = _safe_path(draft_root, safe_name)
    if destination.exists():
        raise ValueError("A draft with this name already exists")
    _atomic_write_text(destination, content)
    return {
        "status": "created",
        "path": str(destination.relative_to(context.workspace_root)),
        "bytes": len(content.encode("utf-8")),
    }


def _mutable_workspace_path(
    context: ToolContext, relative_path: str
) -> tuple[Path, Path]:
    candidate = Path((relative_path or "").strip())
    if not candidate.parts or candidate.is_absolute():
        raise ValueError("A relative workspace path is required")
    if any(part.lower() in IGNORED_PATH_PARTS for part in candidate.parts):
        raise ValueError("Protected workspace directories cannot be changed")
    if _is_sensitive_path(candidate):
        raise ValueError("Secret-bearing files cannot be changed by an agent")
    if candidate.suffix.lower() not in TEXT_FILE_SUFFIXES:
        raise ValueError("Only supported text files can be changed")
    if _has_symlink_component(context.workspace_root, str(candidate)):
        raise ValueError("Symbolic links cannot be changed by an agent")
    return _safe_path(context.workspace_root, str(candidate)), candidate


def _atomic_write_text(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.arc-{secrets.token_hex(8)}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        if path.exists():
            shutil.copystat(path, temporary)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _workspace_update(
    arguments: dict[str, Any], context: ToolContext
) -> dict[str, Any]:
    path, relative = _mutable_workspace_path(context, str(arguments.get("path", "")))
    if not path.exists() and arguments.get("create_if_missing") is True:
        content = str(arguments.get("new_text", ""))
        if not content or len(content) > 200_000:
            raise ValueError("New file content must contain 1 to 200000 characters")
        path.parent.mkdir(parents=True, exist_ok=True)
        if _has_symlink_component(context.workspace_root, str(relative)):
            raise ValueError("Symbolic links cannot be changed by an agent")
        # Exclusive creation cannot overwrite a file created by another job.
        with path.open("x", encoding="utf-8") as destination:
            destination.write(content)
        return {
            "status": "created",
            "path": str(relative),
            "bytes": len(content.encode("utf-8")),
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        }
    if not path.is_file():
        raise ValueError(
            "workspace_update requires an existing file, or create_if_missing=true"
        )
    if path.stat().st_size > 500_000:
        raise ValueError("Files larger than 500 KB cannot be updated by this tool")

    old_text = str(arguments.get("old_text", ""))
    new_text = str(arguments.get("new_text", ""))
    if not old_text:
        raise ValueError("old_text is required and cannot be empty")
    if len(new_text) > 200_000:
        raise ValueError("new_text cannot exceed 200000 characters")
    replace_all = bool(arguments.get("replace_all", False))
    expected_hash = str(arguments.get("expected_sha256", "")).strip().lower()

    content = path.read_text(encoding="utf-8", errors="strict")
    before_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if expected_hash and not hmac.compare_digest(expected_hash, before_hash):
        raise ValueError(
            "File changed after it was read; read it again before updating"
        )
    occurrences = content.count(old_text)
    if occurrences == 0:
        raise ValueError("old_text was not found; no file was changed")
    if occurrences > 1 and not replace_all:
        raise ValueError(
            "old_text occurs more than once; provide more context or set replace_all"
        )

    updated = content.replace(old_text, new_text, -1 if replace_all else 1)
    _atomic_write_text(path, updated)
    return {
        "status": "updated",
        "path": str(relative),
        "replacements": occurrences if replace_all else 1,
        "before_sha256": before_hash,
        "after_sha256": hashlib.sha256(updated.encode("utf-8")).hexdigest(),
    }


def _actor_storage_key(actor_id: str) -> str:
    return hashlib.sha256(actor_id.encode("utf-8")).hexdigest()[:24]


def _workspace_delete(
    arguments: dict[str, Any], context: ToolContext
) -> dict[str, Any]:
    path, relative = _mutable_workspace_path(context, str(arguments.get("path", "")))
    if not path.is_file():
        raise ValueError("workspace_delete can delete only one existing file")
    trash_id = secrets.token_urlsafe(16)
    trash_root = _private_storage(
        context, Path(".arc") / "trash" / _actor_storage_key(context.actor_id)
    )
    trash_directory = trash_root / trash_id
    destination = trash_directory / relative
    destination.parent.mkdir(parents=True, exist_ok=False)
    file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {
        "trash_id": trash_id,
        "original_path": str(relative),
        "sha256": file_hash,
        "deleted_at": _utc_iso(),
        "role": context.role,
    }
    try:
        (trash_directory / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        shutil.move(str(path), str(destination))
    except Exception:
        if destination.is_file() and not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(destination), str(path))
        shutil.rmtree(trash_directory, ignore_errors=True)
        raise
    return {
        "status": "moved_to_trash",
        "path": str(relative),
        "trash_id": trash_id,
        "recoverable": True,
        "sha256": file_hash,
    }


def _workspace_restore(
    arguments: dict[str, Any], context: ToolContext
) -> dict[str, Any]:
    trash_id = str(arguments.get("trash_id", "")).strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,64}", trash_id):
        raise ValueError("Invalid trash_id")
    trash_root = _private_storage(
        context, Path(".arc") / "trash" / _actor_storage_key(context.actor_id)
    )
    trash_directory = _safe_path(trash_root, trash_id)
    manifest_path = trash_directory / "manifest.json"
    if _has_symlink_component(
        context.workspace_root, str(manifest_path.relative_to(context.workspace_root))
    ):
        raise ValueError("Trash metadata cannot contain links or junctions")
    if not manifest_path.is_file():
        raise ValueError("Trash entry does not exist")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    destination, relative = _mutable_workspace_path(
        context,
        str(manifest.get("original_path", "")),
    )
    if destination.exists():
        raise ValueError("Original path is already occupied; restore was not performed")
    trashed_file = _safe_path(trash_directory, str(relative))
    if _has_symlink_component(
        context.workspace_root, str(trashed_file.relative_to(context.workspace_root))
    ):
        raise ValueError("Trashed files cannot contain links or junctions")
    if not trashed_file.is_file():
        raise ValueError("Trashed file is missing")
    expected_hash = str(manifest.get("sha256", ""))
    actual_hash = hashlib.sha256(trashed_file.read_bytes()).hexdigest()
    if not expected_hash or not hmac.compare_digest(expected_hash, actual_hash):
        raise ValueError(
            "Trashed file integrity check failed; restore was not performed"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(trashed_file), str(destination))
    try:
        shutil.rmtree(trash_directory)
    except OSError:
        logger.warning(
            "Restored %s but could not remove its empty trash metadata", relative
        )
    return {"status": "restored", "path": str(relative), "trash_id": trash_id}


async def _terminal_run(
    arguments: dict[str, Any], context: ToolContext
) -> dict[str, Any]:
    """No code is executed in the credential-bearing API process.

    A separately provisioned sandbox worker must isolate filesystem, environment,
    network, CPU, output and process lifetime for the supplied workspace identity.
    """
    argv = _validate_terminal_argv(arguments.get("argv"))
    cwd = str(arguments.get("cwd", "."))
    _safe_path(context.workspace_root, cwd)
    files = {}
    total = 0
    for directory, names, filenames in os.walk(
        context.workspace_root, followlinks=False
    ):
        names[:] = sorted(
            name
            for name in names
            if not name.startswith(".")
            and name.lower() not in IGNORED_PATH_PARTS
            and not _is_sensitive_path(Path(name))
            and not (Path(directory) / name).is_symlink()
        )
        for name in sorted(filenames):
            path = Path(directory) / name
            relative = path.relative_to(context.workspace_root).as_posix()
            if name.startswith(".") or path.suffix.lower() not in TEXT_FILE_SUFFIXES:
                continue
            if _is_sensitive_path(Path(relative)) or _has_symlink_component(
                context.workspace_root, relative
            ):
                continue
            if path.stat().st_nlink > 1:
                continue
            read = _workspace_read({"path": relative, "max_chars": 20_000}, context)
            if read["truncated"]:
                raise ValueError(
                    "A project file is too large for this local terminal snapshot"
                )
            content = read["content"].encode("utf-8")
            total += len(content)
            if len(files) >= 200 or total > 512_000:
                raise ValueError(
                    "The project exceeds the local terminal snapshot limit"
                )
            files[relative] = base64.b64encode(content).decode("ascii")
    return await _connector_call(
        "terminal_run",
        {
            "operation": "run",
            "parameters": {
                "argv": argv,
                "cwd": cwd,
                "files": files,
                "timeout_seconds": min(
                    max(int(arguments.get("timeout_seconds", 60)), 1), 120
                ),
            },
        },
        context,
    )


CONNECTOR_ENV = {
    "terminal_run": ("ARC_TERMINAL_RUNNER_URL", "ARC_TERMINAL_RUNNER_TOKEN"),
    "finance_connector": ("ARC_FINANCE_CONNECTOR_URL", "ARC_FINANCE_CONNECTOR_TOKEN"),
    "crm_connector": ("ARC_CRM_CONNECTOR_URL", "ARC_CRM_CONNECTOR_TOKEN"),
    "cloud_connector": ("ARC_CLOUD_CONNECTOR_URL", "ARC_CLOUD_CONNECTOR_TOKEN"),
}


async def _connector_call(
    connector_name: str,
    arguments: dict[str, Any],
    context: ToolContext,
) -> dict[str, Any]:
    url_env, token_env = CONNECTOR_ENV[connector_name]
    endpoint = os.getenv(url_env, "").strip()
    if not endpoint:
        return {
            "status": "not_configured",
            "connector": connector_name,
            "required_environment": [url_env, token_env],
        }
    allowed_actors = {
        item.strip()
        for item in os.getenv("ARC_CONNECTOR_ALLOWED_ACTORS", "").split(",")
        if item.strip()
    }
    paired_terminal = connector_name == "terminal_run" and terminal_is_connected(
        context.actor_id
    )
    if context.actor_id not in allowed_actors and not paired_terminal:
        return {
            "status": "denied",
            "connector": connector_name,
            "message": "This session has not been provisioned for this gateway by its administrator.",
        }
    parsed = urlparse(endpoint)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError(f"{url_env} must be an http or https URL")
    if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("Remote connector URLs must use HTTPS")

    operation = str(arguments.get("operation", "")).strip()
    parameters = arguments.get("parameters", {})
    if not operation or len(operation) > 200:
        raise ValueError("operation must contain between 1 and 200 characters")
    if not isinstance(parameters, dict):
        raise ValueError("parameters must be an object")

    token = os.getenv(token_env, "").strip()
    if not token:
        return {
            "status": "not_configured",
            "connector": connector_name,
            "required_environment": [token_env],
        }
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload = {
        "actor_id": context.actor_id,
        "workspace_id": _actor_storage_key(context.actor_id)
        + "/"
        + _actor_storage_key(context.session_id),
        "role": context.role,
        "session_id": context.session_id,
        "operation": operation,
        "parameters": parameters,
    }
    serialized_payload = json.dumps(payload, ensure_ascii=False)
    payload_limit = 900_000 if connector_name == "terminal_run" else 100_000
    if len(serialized_payload.encode("utf-8")) > payload_limit:
        raise ValueError("Connector request exceeds its size limit")
    request_timeout = 140.0 if connector_name == "terminal_run" else 30.0
    async with httpx.AsyncClient(
        timeout=request_timeout, follow_redirects=False
    ) as client:
        async with client.stream(
            "POST", endpoint, headers=headers, content=serialized_payload
        ) as response:
            response.raise_for_status()
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > 1_000_000:
                    raise ValueError("Connector response exceeds the 1 MB limit")
                chunks.append(chunk)
            response_content = b"".join(chunks)
            content_type = response.headers.get("content-type", "")
    if "json" in content_type:
        result: Any = json.loads(response_content.decode("utf-8"))
    else:
        result = response_content.decode("utf-8", errors="replace")
    serialized = (
        json.dumps(result, ensure_ascii=False)
        if not isinstance(result, str)
        else result
    )
    if len(serialized) > MAX_TOOL_OUTPUT_CHARS:
        result = serialized[:MAX_TOOL_OUTPUT_CHARS] + "...[truncated]"
    return {"status": "completed", "connector": connector_name, "result": result}


def _connector_handler(name: str) -> Callable[[dict[str, Any], ToolContext], Any]:
    async def handler(
        arguments: dict[str, Any], context: ToolContext
    ) -> dict[str, Any]:
        return await _connector_call(name, arguments, context)

    return handler


def _validate_repository_and_branch(repository: str, branch: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", repository):
        raise ValueError("repository must use the owner/name format")
    if (
        not branch
        or len(branch) > 200
        or branch.startswith(("/", "."))
        or branch.endswith(("/", "."))
        or ".." in branch
        or "@{" in branch
        or not re.fullmatch(r"[A-Za-z0-9_./-]+", branch)
    ):
        raise ValueError("branch is not a valid Git branch name")


def _git_publish(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Queue a bounded publish manifest for a separately trusted GitHub App worker."""
    repository = str(arguments.get("repository", "")).strip()
    branch = str(arguments.get("branch", "")).strip()
    _validate_repository_and_branch(repository, branch)
    base_commit = str(arguments.get("base_commit", "")).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40,64}", base_commit):
        raise ValueError(
            "base_commit must be the exact 40-64 character commit hash reviewed by the user"
        )
    commit_message = str(arguments.get("commit_message", "")).strip()
    if not commit_message or len(commit_message) > 200 or "\n" in commit_message:
        raise ValueError("commit_message must be one line containing 1-200 characters")
    paths = [
        _scope_path(item) for item in _string_list(arguments.get("paths"), "paths")
    ]
    if len(set(paths)) != len(paths):
        raise ValueError("paths cannot contain duplicates")

    snapshot: list[dict[str, Any]] = []
    for relative_path in paths:
        path, normalized = _mutable_workspace_path(context, relative_path)
        if path.exists() and not path.is_file():
            raise ValueError(f"'{relative_path}' is not a file")
        if path.is_file() and path.stat().st_size > 500_000:
            raise ValueError(f"'{relative_path}' exceeds the 500 KB publish-job limit")
        snapshot.append(
            {
                "path": normalized.as_posix(),
                "state": "present" if path.is_file() else "deleted",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()
                if path.is_file()
                else None,
            }
        )

    job_id = secrets.token_urlsafe(18)
    get_agent_store().create_publish_job(
        {
            "job_id": job_id,
            "actor_id": context.actor_id,
            "role": context.role,
            "session_id": context.session_id,
            "repository": repository,
            "branch": branch,
            "base_commit": base_commit,
            "commit_message": commit_message,
            "paths": paths,
            "snapshot": snapshot,
        }
    )
    return {
        "status": "queued",
        "job_id": job_id,
        "repository": repository,
        "branch": branch,
        "paths": paths,
        "published": False,
        "message": (
            "The reviewed publish job is queued. A repository-scoped GitHub App worker "
            "must verify the base commit and file hashes before publishing it."
        ),
    }


async def _delegate_agent(
    arguments: dict[str, Any], context: ToolContext
) -> dict[str, Any]:
    agent_id = (
        str(arguments.get("agent", arguments.get("department", ""))).strip().lower()
    )
    task = str(arguments.get("task", "")).strip()
    if not task or len(task) > 4_000:
        raise ValueError("task must contain between 1 and 4000 characters")
    if context.delegation_depth >= 2:
        raise ValueError("Maximum delegation depth reached")

    from company.organization import allowed_delegate_targets
    from company.runtime import run_company_agent

    allowed = allowed_delegate_targets(context.role)
    if not allowed:
        raise ValueError(f"Agent '{context.role}' has no direct reports")
    if agent_id not in allowed:
        raise ValueError(
            f"Agent '{context.role}' may delegate only to direct reports: "
            + ", ".join(allowed)
        )

    from company.work_runtime import queue_delegation

    queued = queue_delegation(
        context.actor_id,
        context.session_id,
        agent_id,
        task,
        manager=context.role,
        group_id=context.company_group_id,
    )
    if queued is not None:
        return queued
    return await run_company_agent(
        agent_id=agent_id,
        prompt=task,
        session_id=context.session_id,
        delegation_depth=context.delegation_depth + 1,
        actor_id=context.actor_id,
        requested_by=context.role,
        group_id=context.company_group_id,
    )


async def _delegate_department(
    arguments: dict[str, Any],
    context: ToolContext,
) -> dict[str, Any]:
    """Backward-compatible handler for already persisted tool calls."""
    return await _delegate_agent(arguments, context)


OBJECT_SCHEMA = {"type": "object", "additionalProperties": True}


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "calculator": ToolSpec(
        name="calculator",
        description="Evaluate deterministic arithmetic without using model estimation.",
        parameters={
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
            "additionalProperties": False,
        },
        risk=LOW_RISK,
        handler=_calculate,
    ),
    "finance_summary": ToolSpec(
        name="finance_summary",
        description="Calculate income, expenses, net cash flow, and category totals.",
        parameters={
            "type": "object",
            "properties": {
                "transactions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "kind": {"type": "string", "enum": ["income", "expense"]},
                            "amount": {"type": "number", "minimum": 0},
                            "category": {"type": "string"},
                        },
                        "required": ["kind", "amount"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["transactions"],
            "additionalProperties": False,
        },
        risk=LOW_RISK,
        handler=_finance_summary,
    ),
    "workspace_search": ToolSpec(
        name="workspace_search",
        description="Search text files inside the configured ARC workspace.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "path": {
                    "type": "string",
                    "description": "Relative directory or file path.",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        risk=LOW_RISK,
        handler=_workspace_search,
    ),
    "workspace_read": ToolSpec(
        name="workspace_read",
        description="Read a project text file by relative path, such as shipping.py. Do not invent an absolute /workspace path.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "max_chars": {"type": "integer", "minimum": 1, "maximum": 20000},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        risk=LOW_RISK,
        handler=_workspace_read,
    ),
    "workspace_update": ToolSpec(
        name="workspace_update",
        description=(
            "Update exact text in a project file. For a NEW file, use create_if_missing=true, old_text=an empty string, and new_text=the complete content. Existing files are never replaced by creation mode. An optional read hash prevents stale updates."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
                "expected_sha256": {"type": "string"},
                "replace_all": {"type": "boolean", "default": False},
                "create_if_missing": {"type": "boolean", "default": False},
            },
            "required": ["path", "old_text", "new_text"],
            "additionalProperties": False,
        },
        risk=WRITE_RISK,
        handler=_workspace_update,
    ),
    "workspace_delete": ToolSpec(
        name="workspace_delete",
        description="Move one reviewed workspace file to Arc Company trash so it can be restored.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
        risk=RECOVERABLE_DELETE_RISK,
        handler=_workspace_delete,
    ),
    "workspace_restore": ToolSpec(
        name="workspace_restore",
        description="Restore one file from the authenticated user's Arc Company trash.",
        parameters={
            "type": "object",
            "properties": {"trash_id": {"type": "string"}},
            "required": ["trash_id"],
            "additionalProperties": False,
        },
        risk=WRITE_RISK,
        handler=_workspace_restore,
    ),
    "draft_file": ToolSpec(
        name="draft_file",
        description="Create a draft only under .arc/drafts after explicit user approval.",
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string"}, "content": {"type": "string"}},
            "required": ["name", "content"],
            "additionalProperties": False,
        },
        risk=APPROVAL_REQUIRED,
        handler=_draft_file,
    ),
    "terminal_run": ToolSpec(
        name="terminal_run",
        description=(
            "Run an approved, allowlisted command without a shell. Supports read-only git, rg, "
            "Flutter/Dart analysis or tests, and pytest."
        ),
        parameters={
            "type": "object",
            "properties": {
                "argv": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "cwd": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 120},
            },
            "required": ["argv"],
            "additionalProperties": False,
        },
        risk=APPROVAL_REQUIRED,
        handler=_terminal_run,
    ),
    "finance_connector": ToolSpec(
        name="finance_connector",
        description="Call the configured finance/accounting connector after approval.",
        parameters={
            "type": "object",
            "properties": {
                "operation": {"type": "string"},
                "parameters": OBJECT_SCHEMA,
            },
            "required": ["operation"],
            "additionalProperties": False,
        },
        risk=APPROVAL_REQUIRED,
        handler=_connector_handler("finance_connector"),
    ),
    "crm_connector": ToolSpec(
        name="crm_connector",
        description="Call the configured CRM or marketing connector after approval.",
        parameters={
            "type": "object",
            "properties": {
                "operation": {"type": "string"},
                "parameters": OBJECT_SCHEMA,
            },
            "required": ["operation"],
            "additionalProperties": False,
        },
        risk=APPROVAL_REQUIRED,
        handler=_connector_handler("crm_connector"),
    ),
    "cloud_connector": ToolSpec(
        name="cloud_connector",
        description="Call the configured cloud-service gateway after approval.",
        parameters={
            "type": "object",
            "properties": {
                "operation": {"type": "string"},
                "parameters": OBJECT_SCHEMA,
            },
            "required": ["operation"],
            "additionalProperties": False,
        },
        risk=APPROVAL_REQUIRED,
        handler=_connector_handler("cloud_connector"),
    ),
    "git_publish": ToolSpec(
        name="git_publish",
        description=(
            "Queue an exact reviewed file set for a repository-scoped GitHub App worker. "
            "Queuing does not claim that the files were published."
        ),
        parameters={
            "type": "object",
            "properties": {
                "repository": {
                    "type": "string",
                    "description": "Git repository as owner/name.",
                },
                "branch": {"type": "string"},
                "base_commit": {"type": "string"},
                "commit_message": {"type": "string"},
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 20,
                },
            },
            "required": [
                "repository",
                "branch",
                "base_commit",
                "commit_message",
                "paths",
            ],
            "additionalProperties": False,
        },
        risk=EXTERNAL_RISK,
        handler=_git_publish,
    ),
    "delegate_agent": ToolSpec(
        name="delegate_agent",
        description=(
            "Delegate a bounded task to one direct-report employee. The backend "
            "enforces the company reporting hierarchy."
        ),
        parameters={
            "type": "object",
            "properties": {
                "agent": {"type": "string"},
                "task": {"type": "string"},
            },
            "required": ["agent", "task"],
            "additionalProperties": False,
        },
        risk=LOW_RISK,
        handler=_delegate_agent,
    ),
    "delegate_department": ToolSpec(
        name="delegate_department",
        description="Deprecated compatibility alias for delegate_agent.",
        parameters={
            "type": "object",
            "properties": {
                "department": {"type": "string"},
                "task": {"type": "string"},
            },
            "required": ["department", "task"],
            "additionalProperties": False,
        },
        risk=LOW_RISK,
        handler=_delegate_department,
    ),
}


def tool_schemas(tool_names: tuple[str, ...]) -> list[dict[str, Any]]:
    return [TOOL_REGISTRY[name].openai_schema() for name in tool_names]


def public_tool_catalog(tool_names: tuple[str, ...]) -> list[dict[str, Any]]:
    catalog = []
    for name in tool_names:
        spec = TOOL_REGISTRY[name]
        risk = "dynamic" if callable(spec.risk) else spec.risk
        item: dict[str, Any] = {
            "name": name,
            "description": spec.description,
            "risk": risk,
        }
        if name in CONNECTOR_ENV:
            url_env, token_env = CONNECTOR_ENV[name]
            item["configured"] = bool(
                os.getenv(url_env, "").strip()
                and os.getenv(token_env, "").strip()
                and os.getenv("ARC_CONNECTOR_ALLOWED_ACTORS", "").strip()
            )
            item["configuration"] = [url_env, token_env]
        catalog.append(item)
    return catalog


def _default_permission_mode(
    spec: ToolSpec, arguments: dict[str, Any] | None = None
) -> str:
    risk = spec.risk_for(arguments or {})
    return "allow" if risk == LOW_RISK else "ask"


def _scope_path(value: Any) -> str:
    candidate = Path(str(value or "").strip())
    if not candidate.parts or candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("Permission paths must be workspace-relative")
    if any(part.lower() in IGNORED_PATH_PARTS for part in candidate.parts):
        raise ValueError("Permission paths cannot include protected directories")
    if _is_sensitive_path(candidate):
        raise ValueError("Permission paths cannot target secret-bearing files")
    return candidate.as_posix()


def _string_list(value: Any, field: str, *, maximum: int = 20) -> list[str]:
    if not isinstance(value, list) or not value or len(value) > maximum:
        raise ValueError(
            f"scope.{field} must be a non-empty list with at most {maximum} items"
        )
    cleaned = [str(item).strip() for item in value]
    if any(not item or len(item) > 500 for item in cleaned):
        raise ValueError(f"scope.{field} contains an invalid value")
    return cleaned


def _normalize_permission_scope(
    tool_name: str,
    mode: str,
    scope: dict[str, Any] | None,
) -> dict[str, Any]:
    """Validate the exact boundary of a temporary automatic permission."""
    if mode != "allow" or TOOL_REGISTRY[tool_name].risk_for({}) == LOW_RISK:
        return {}
    if not isinstance(scope, dict):
        raise ValueError("A scope object is required for automatic privileged actions")

    if tool_name in {"workspace_update", "workspace_delete"}:
        paths = _string_list(scope.get("paths"), "paths")
        return {"paths": sorted({_scope_path(path) for path in paths})}
    if tool_name == "workspace_restore":
        trash_ids = _string_list(scope.get("trash_ids"), "trash_ids")
        if any(not re.fullmatch(r"[A-Za-z0-9_-]{16,64}", item) for item in trash_ids):
            raise ValueError("scope.trash_ids contains an invalid trash ID")
        return {"trash_ids": sorted(set(trash_ids))}
    if tool_name == "draft_file":
        names = _string_list(scope.get("names"), "names")
        safe_names = []
        for name in names:
            if Path(name).name != name or name in {".", ".."}:
                raise ValueError("scope.names must contain file names, not paths")
            safe_names.append(name)
        return {"names": sorted(set(safe_names))}
    if tool_name == "terminal_run":
        argv = _validate_terminal_argv(scope.get("argv"))
        normalized: dict[str, Any] = {"argv": argv}
        if "cwd" in scope:
            normalized["cwd"] = _scope_path(scope["cwd"])
        return normalized
    if tool_name in CONNECTOR_ENV:
        operations = _string_list(scope.get("operations"), "operations")
        return {"operations": sorted(set(operations))}
    if tool_name == "git_publish":
        repository = str(scope.get("repository", "")).strip()
        branch = str(scope.get("branch", "")).strip()
        _validate_repository_and_branch(repository, branch)
        paths = _string_list(scope.get("paths"), "paths")
        return {
            "repository": repository,
            "branch": branch,
            "paths": sorted({_scope_path(path) for path in paths}),
        }
    raise ValueError(f"Tool '{tool_name}' cannot receive an automatic privileged grant")


def _scope_allows(
    tool_name: str, arguments: dict[str, Any], scope: dict[str, Any]
) -> bool:
    try:
        if TOOL_REGISTRY[tool_name].risk_for(arguments) == LOW_RISK:
            return True
        if tool_name in {"workspace_update", "workspace_delete"}:
            return _scope_path(arguments.get("path")) in scope.get("paths", [])
        if tool_name == "workspace_restore":
            return str(arguments.get("trash_id", "")) in scope.get("trash_ids", [])
        if tool_name == "draft_file":
            return str(arguments.get("name", "")) in scope.get("names", [])
        if tool_name == "terminal_run":
            argv = _validate_terminal_argv(arguments.get("argv"))
            cwd_matches = (
                "cwd" not in scope
                or _scope_path(arguments.get("cwd", ".")) == scope["cwd"]
            )
            return argv == scope.get("argv", []) and cwd_matches
        if tool_name in CONNECTOR_ENV:
            return str(arguments.get("operation", "")).strip() in scope.get(
                "operations", []
            )
        if tool_name == "git_publish":
            requested_paths = sorted(
                {_scope_path(path) for path in arguments.get("paths", [])}
            )
            return (
                str(arguments.get("repository", "")).strip() == scope.get("repository")
                and str(arguments.get("branch", "")).strip() == scope.get("branch")
                and requested_paths == sorted(scope.get("paths", []))
            )
    except (TypeError, ValueError):
        return False
    return False


def get_effective_permission(
    actor_id: str,
    role: str,
    session_id: str,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    spec = TOOL_REGISTRY[tool_name]
    configured = get_agent_store().get_permission(actor_id, role, session_id, tool_name)
    default = _default_permission_mode(spec, arguments)
    return {
        "role": role,
        "session_id": session_id,
        "tool": tool_name,
        "mode": configured["mode"] if configured else default,
        "source": "user" if configured else "default",
        "default": default,
        "risk": spec.risk_for(arguments or {}),
        "scope": configured.get("scope", {}) if configured else {},
        "expires_at": _utc_iso(float(configured["expires_at"])) if configured else None,
        "remaining_uses": int(configured["remaining_uses"]) if configured else None,
    }


def set_tool_permission(
    actor_id: str,
    role: str,
    session_id: str,
    tool_name: str,
    mode: str,
    duration_minutes: int,
    max_uses: int,
    scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_role, allowed_tools = _allowed_tools_for_role(role)
    if tool_name not in allowed_tools or tool_name not in TOOL_REGISTRY:
        raise ValueError(
            f"Tool '{tool_name}' is not available to role '{normalized_role}'"
        )
    normalized_mode = (mode or "").strip().lower()
    if normalized_mode not in VALID_PERMISSION_MODES:
        raise ValueError("Permission mode must be allow, ask, or deny")
    if not session_id or len(session_id) > 64:
        raise ValueError("session_id must contain between 1 and 64 characters")
    safe_duration = min(max(int(duration_minutes), 1), 60)
    safe_uses = min(max(int(max_uses), 1), 20)
    normalized_scope = _normalize_permission_scope(tool_name, normalized_mode, scope)
    get_agent_store().set_permission(
        actor_id,
        normalized_role,
        session_id,
        tool_name,
        normalized_mode,
        normalized_scope,
        expires_at=time.time() + safe_duration * 60,
        max_uses=safe_uses,
    )
    return get_effective_permission(actor_id, normalized_role, session_id, tool_name)


def reset_tool_permission(
    actor_id: str,
    role: str,
    session_id: str,
    tool_name: str,
) -> dict[str, Any]:
    normalized_role, allowed_tools = _allowed_tools_for_role(role)
    if tool_name not in allowed_tools or tool_name not in TOOL_REGISTRY:
        raise ValueError(
            f"Tool '{tool_name}' is not available to role '{normalized_role}'"
        )
    get_agent_store().delete_permission(
        actor_id, normalized_role, session_id, tool_name
    )
    return get_effective_permission(actor_id, normalized_role, session_id, tool_name)


def _allowed_tools_for_role(role: str) -> tuple[str, tuple[str, ...]]:
    normalized = (role or "").strip().lower()
    from company.organization import get_profile

    profile = get_profile(normalized)
    return profile.slug, profile.tool_names


def role_permission_catalog(
    actor_id: str, role: str, session_id: str
) -> list[dict[str, Any]]:
    normalized_role, tool_names = _allowed_tools_for_role(role)
    return [
        get_effective_permission(actor_id, normalized_role, session_id, tool_name)
        for tool_name in tool_names
    ]


def permission_catalog(actor_id: str, session_id: str) -> list[dict[str, Any]]:
    from company.organization import PROFILES

    return [
        get_effective_permission(actor_id, profile.slug, session_id, tool_name)
        for profile in PROFILES.values()
        for tool_name in profile.tool_names
    ]


async def _execute(
    spec: ToolSpec, arguments: dict[str, Any], context: ToolContext
) -> dict[str, Any]:
    try:
        result = spec.handler(arguments, context)
        if inspect.isawaitable(result):
            result = await result
        safe_result = _redact(result)
        _audit("tool_completed", context, spec.name, result=safe_result)
        return {"status": "completed", "tool": spec.name, "output": safe_result}
    except (ValueError, TypeError, OSError, httpx.HTTPError) as error:
        # Transport errors can contain private gateway URLs; OS errors contain
        # host paths. Neither belongs in model context or user-visible audit data.
        if isinstance(error, httpx.HTTPError):
            message = "The connected service is temporarily unavailable"
        elif isinstance(error, OSError):
            message = "The workspace operation could not be completed"
        elif isinstance(error, TypeError):
            message = "Invalid tool input"
        else:
            message = str(error)
        _audit("tool_failed", context, spec.name, error=type(error).__name__)
        return {"status": "failed", "tool": spec.name, "error": message}
    except Exception as error:
        logger.exception("Unexpected failure in tool %s", spec.name)
        _audit("tool_failed", context, spec.name, error=type(error).__name__)
        return {"status": "failed", "tool": spec.name, "error": "Tool execution failed"}


async def dispatch_tool(
    allowed_tool_names: tuple[str, ...],
    tool_name: str,
    arguments: dict[str, Any],
    context: ToolContext,
    force_one_time_approval: bool = False,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if tool_name not in allowed_tool_names or tool_name not in TOOL_REGISTRY:
        _audit("tool_denied", context, tool_name, reason="role_permission")
        return {
            "status": "denied",
            "tool": tool_name,
            "error": f"Tool '{tool_name}' is not allowed for role '{context.role}'",
        }, None

    spec = TOOL_REGISTRY[tool_name]
    if len(json.dumps(arguments, default=str).encode("utf-8")) > 100_000:
        return {
            "status": "denied",
            "tool": tool_name,
            "error": "Tool arguments exceed 100 KB",
        }, None
    if _contains_secret_field(arguments):
        _audit("tool_denied", context, tool_name, reason="secret_material")
        return {
            "status": "denied",
            "tool": tool_name,
            "error": "Secret fields cannot be passed to agent tools.",
        }, None
    risk = spec.risk_for(arguments)
    store = get_agent_store()
    global_mode = store.get_approval_mode(context.actor_id)
    if tool_name == "terminal_run" and terminal_is_connected(context.actor_id):
        global_mode = "allow"
    from company.work_policy import local_permission

    autonomous = local_permission(context.actor_id, context.session_id, tool_name)
    if autonomous == "deny":
        return {
            "status": "denied",
            "tool": tool_name,
            "error": "This action is outside the approved continuous-work scope or the company is paused.",
        }, None
    if autonomous == "allow":
        global_mode = "allow"
    configured = store.get_permission(
        context.actor_id, context.role, context.session_id, tool_name
    )
    permission_mode = global_mode
    if configured and configured["mode"] == "deny":
        _audit("tool_denied", context, tool_name, reason="explicit_deny")
        return {
            "status": "denied",
            "tool": tool_name,
            "error": "Tool permission is denied",
        }, None
    if configured:
        permission_mode = "ask"
        if (
            global_mode == "allow"
            and not force_one_time_approval
            and configured["mode"] == "allow"
            and _scope_allows(tool_name, arguments, configured["scope"])
        ):
            # Checking scope and consuming one use must share the store lock.
            grant = store.consume_permission(
                context.actor_id,
                context.role,
                context.session_id,
                tool_name,
                arguments,
                lambda scope: _scope_allows(tool_name, arguments, scope),
            )
            if grant:
                permission_mode = "allow"
    if force_one_time_approval:
        permission_mode = "ask"
    if permission_mode == "allow":
        _audit(
            "tool_auto_approved",
            context,
            tool_name,
            permission_source="global_setting",
            risk=risk,
        )
        return await _execute(spec, arguments, context), None

    approval_id = secrets.token_urlsafe(18)
    approval_token = secrets.token_urlsafe(32)
    now = time.time()
    pending = {
        "approval_id": approval_id,
        "token_digest": hashlib.sha256(approval_token.encode("utf-8")).hexdigest(),
        "role": context.role,
        "session_id": context.session_id,
        "actor_id": context.actor_id,
        "tool_name": tool_name,
        "arguments": arguments,
        "created_at": now,
        "expires_at": now + APPROVAL_TTL_SECONDS,
    }
    get_agent_store().create_pending_action(pending)
    _audit(
        "approval_requested",
        context,
        tool_name,
        approval_id=approval_id,
        arguments=arguments,
    )
    public = {
        "approval_id": approval_id,
        "approval_token": approval_token,
        "tool": tool_name,
        "role": context.role,
        "arguments": _redact(arguments),
        "expires_at": _utc_iso(float(pending["expires_at"])),
        "permission_mode": "ask",
    }
    return {
        "status": "approval_required",
        "tool": tool_name,
        "approval_id": approval_id,
        "message": "The backend did not execute this action. Explicit approval is required.",
    }, public


async def resolve_pending_action(
    approval_id: str,
    approval_token: str | None,
    session_id: str,
    approve: bool,
    actor_id: str = "local",
) -> dict[str, Any]:
    store = get_agent_store()
    pending = store.get_pending_action(approval_id)
    if pending is None:
        raise ValueError("Approval request does not exist or has expired")
    supplied_digest = (
        hashlib.sha256(approval_token.encode("utf-8")).hexdigest()
        if approval_token is not None
        else None
    )
    if (
        pending["session_id"] != session_id
        or pending["actor_id"] != actor_id
        or (
            supplied_digest is not None
            and not hmac.compare_digest(pending["token_digest"], supplied_digest)
        )
    ):
        raise PermissionError("Approval token or session is invalid")

    context = ToolContext(
        role=pending["role"],
        session_id=pending["session_id"],
        actor_id=pending["actor_id"],
        workspace_root=_workspace_root(pending["actor_id"], pending["session_id"]),
    )
    if not approve:
        if not store.resolve_pending_action(approval_id, "denied"):
            raise ValueError("Approval request was already resolved or expired")
        _audit(
            "approval_denied", context, pending["tool_name"], approval_id=approval_id
        )
        return {
            "status": "denied",
            "approval_id": approval_id,
            "tool": pending["tool_name"],
        }

    policy = store.get_permission(
        actor_id, pending["role"], session_id, pending["tool_name"]
    )
    if policy and policy["mode"] == "deny":
        store.resolve_pending_action(approval_id, "denied")
        _audit(
            "tool_denied", context, pending["tool_name"], reason="revoked_after_request"
        )
        return {
            "status": "denied",
            "approval_id": approval_id,
            "tool": pending["tool_name"],
        }
    if not store.resolve_pending_action(approval_id, "approved"):
        raise ValueError("Approval request was already resolved or expired")
    _audit("approval_granted", context, pending["tool_name"], approval_id=approval_id)
    spec = TOOL_REGISTRY[pending["tool_name"]]
    result = await _execute(spec, pending["arguments"], context)
    return {"approval_id": approval_id, **result}


def make_tool_context(
    role: str,
    session_id: str,
    delegation_depth: int = 0,
    actor_id: str = "local",
    company_group_id: str | None = None,
) -> ToolContext:
    return ToolContext(
        role=role,
        session_id=session_id,
        actor_id=actor_id,
        workspace_root=_workspace_root(actor_id, session_id),
        delegation_depth=delegation_depth,
        company_group_id=company_group_id,
    )
