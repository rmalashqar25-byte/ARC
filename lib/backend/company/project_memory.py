"""A small, durable Markdown memory scoped to one browser actor and project."""

import hashlib
import os
import re
import time
import uuid

from agent_store import get_agent_store


def _store():
    return get_agent_store().work_store


def _path(actor, session):
    db = _store()
    digest = hashlib.sha256(f"{actor}\0{session}".encode()).hexdigest()
    return db.path.parent / "project-memory" / f"{digest}.md"


def _clean(value, limit=1200):
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    return value[:limit]


def _render(rows):
    sections = (
        ("goal", "Project goals"),
        ("task", "What the team should do"),
        ("lesson", "Blockers and lessons"),
        ("outcome", "Verified results"),
    )
    lines = ["# Project memory", "", "Saved for this browser workspace and project.", ""]
    for kind, heading in sections:
        notes = [row["content"] for row in rows if row["kind"] == kind]
        lines.extend([f"## {heading}", ""])
        lines.extend(f"- {note}" for note in notes[-8:])
        if not notes:
            lines.append("- Nothing saved yet.")
        lines.append("")
    return "\n".join(lines)


def read(actor, session):
    db = _store()
    if db is None:
        return _render([])
    with db.connection() as connection:
        rows = connection.execute(
            "SELECT note_key, kind, content FROM project_memory WHERE actor=? AND session=? "
            "ORDER BY updated DESC LIMIT 100",
            (actor, session),
        ).fetchall()
    notes = [dict(row) for row in reversed(rows)]
    existing = {row["note_key"] for row in notes}
    # Older projects gain memory from durable task records without model calls.
    tasks = db.list(actor, session)[:8]
    if tasks and not any(note["kind"] == "goal" for note in notes):
        notes.append({"kind": "goal", "content": _clean(tasks[-1].get("description"))})
    for task in reversed(tasks):
        if "task:" + task["id"] not in existing:
            notes.append({"kind": "task", "content": _clean(task.get("description"))})
        if task["status"] in {"completed", "blocked"}:
            kind = "outcome" if task["status"] == "completed" else "lesson"
            if kind + ":" + task["id"] not in existing:
                value = _clean(task.get("result") or task.get("feedback"))
                if value:
                    notes.append({"kind": kind, "content": value})
    if not any(note["kind"] == "lesson" for note in notes):
        events = get_agent_store().list_company_events(actor, session, limit=500)
        for event in events[-100:]:
            if event["event_type"] == "work_blocked":
                notes.append({"kind": "lesson", "content": _clean(event["content"], 500)})
    return _render(notes)


def remember(actor, session, key, kind, content):
    db = _store()
    if db is None or kind not in {"goal", "task", "lesson", "outcome"}:
        return
    content = _clean(content)
    if not content:
        return
    with db.connection() as connection:
        connection.execute(
            "INSERT INTO project_memory(actor,session,note_key,kind,content,updated) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(actor,session,note_key) DO UPDATE SET "
            "kind=excluded.kind, content=excluded.content, updated=excluded.updated",
            (actor, session, key, kind, content, time.time()),
        )
    path = _path(actor, session)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(read(actor, session), encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, path)
