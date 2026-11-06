"""Bounded app delivery: generate files, validate, check in isolation, then publish."""

import asyncio
import json
import logging
from pathlib import PurePosixPath

from agent_tools import dispatch_tool, make_tool_context
from developer_connections import connection, create_completion

from company.collaboration import record_agent_report, record_delegation
from company.organization import get_profile
from company.work_policy import model_gate

LOG = logging.getLogger("uvicorn.error")
CHECK = """import pathlib, subprocess

def test_application_artifacts():
    assert pathlib.Path("index.html").is_file()
    assert pathlib.Path("app.js").is_file()
    assert pathlib.Path("test_app.js").is_file()
    assert "node:test" in pathlib.Path("test_app.js").read_text()
    for path in pathlib.Path(".").rglob("*.js"):
        subprocess.run(["node", "--check", str(path)], check=True, capture_output=True, text=True)
    result = subprocess.run(["node", "--test", "test_app.js"], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "# tests 0" not in result.stdout, "No JavaScript tests ran"
"""


def parse_files(content):
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    value = json.loads(text)
    files = value.get("files")
    if not isinstance(files, dict) or not 4 <= len(files) <= 10:
        raise ValueError("The developer did not return a bounded project file set")
    if not {"index.html", "app.js", "test_app.js", "README.md"} <= files.keys():
        raise ValueError(
            "The generated project is missing its app, tests, or instructions"
        )
    total = 0
    for name, body in files.items():
        path = PurePosixPath(name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "\\" in name
            or any(p.startswith(".") or ":" in p for p in path.parts)
            or path.suffix not in {".html", ".css", ".js", ".json", ".md"}
            or not isinstance(body, str)
            or not body.strip()
            or len(body) > 20000
        ):
            raise ValueError("The developer returned an invalid project file")
        total += len(body.encode())
    if total > 100000:
        raise ValueError("The generated project exceeds its delivery limit")
    return files


async def build_project(task):
    own = connection()
    if not own:
        return {
            "status": "blocked",
            "message": "Select a model connection before building.",
        }
    actor, session = task["actor"], task["session"]
    group = record_delegation(
        actor_id=actor,
        session_id=session,
        sender_id="ceo",
        recipient_id="cto",
        task=task["description"],
    )
    record_delegation(
        actor_id=actor,
        session_id=session,
        sender_id="cto",
        recipient_id="app_developer",
        task="Implement the requested browser app with real files and executable tests.",
        group_id=group["group_id"],
    )
    profile = get_profile("app_developer")
    context = make_tool_context("app_developer", session, 2, actor, group["group_id"])
    brief = (
        "Implement the founder's small browser application now. Return ONE JSON object "
        '{"files":{"index.html":"complete content","app.js":"complete content",'
        '"test_app.js":"complete content","README.md":"run instructions"}}. '
        "Optional style.css is allowed. No other prose. No external packages, CDN, API keys, "
        "network calls, placeholders or build tools. The app runs by opening index.html. "
        "Use plain JavaScript. app.js must work both in the browser and when required by Node; "
        "guard DOM access with typeof document. Export pure core functions via module.exports "
        "when module exists. test_app.js must use node:test and node:assert/strict, require "
        "./app.js, and test real core behavior and errors. For a calculator, export calculate(a,op,b) "
        "and test +,-,*,/, decimals and divide by zero. Keep every file short and complete. "
        "Do not use eval. The controller will write files, run tests and publish; do not claim these actions."
    )
    problem = ""
    for attempt in range(2):
        LOG.info(
            "ARC artifact stage=generate task=%s attempt=%s", task["id"], attempt + 1
        )
        model_gate(own["model"])
        response = await asyncio.to_thread(
            create_completion,
            own,
            8192,
            messages=[
                {"role": "system", "content": brief},
                {"role": "user", "content": task["description"] + problem},
            ],
            response_format={"type": "json_object"},
        )
        try:
            files = parse_files(response.choices[0].message.content or "")
        except (ValueError, TypeError, AttributeError) as error:
            problem = "\nPrevious output could not be used: " + str(error)[:200]
            continue
        files["test_arc_generated.py"] = CHECK
        for name, body in files.items():
            # Use the same permission, path, hash and audit controls as agent tools.
            from agent_tools import _workspace_read

            try:
                previous = _workspace_read({"path": name, "max_chars": 20000}, context)
            except ValueError:
                previous = None
            arguments = {
                "path": name,
                "old_text": previous["content"] if previous else "",
                "new_text": body,
                "create_if_missing": previous is None,
            }
            if previous:
                arguments["expected_sha256"] = previous["sha256"]
            result, pending = await dispatch_tool(
                profile.tool_names, "workspace_update", arguments, context
            )
            if pending or result.get("status") != "completed":
                return {
                    "status": "blocked",
                    "message": "Project file writing needs attention: "
                    + str(result.get("error") or result.get("status")),
                }
        LOG.info("ARC artifact stage=check task=%s files=%s", task["id"], len(files))
        result, pending = await dispatch_tool(
            profile.tool_names,
            "terminal_run",
            {
                "argv": ["python3", "-m", "pytest", "-q", "test_arc_generated.py"],
                "cwd": ".",
                "timeout_seconds": 60,
            },
            context,
        )
        output = result.get("output", {}).get("result", {})
        if (
            not pending
            and result.get("status") == "completed"
            and output.get("exit_code") == 0
        ):
            message = (
                "Created "
                + ", ".join(files)
                + ". JavaScript syntax and executable application tests passed in the isolated project runner."
            )
            record_agent_report(
                actor_id=actor,
                session_id=session,
                sender_id="app_developer",
                recipient_id="cto",
                content=message,
                group_id=group["group_id"],
            )
            record_agent_report(
                actor_id=actor,
                session_id=session,
                sender_id="cto",
                recipient_id="ceo",
                content="Implementation files were created and isolated application checks passed. GitHub delivery is the next stage; no push is claimed yet.",
                group_id=group["group_id"],
            )
            return {"message": message}
        problem = (
            "\nRepair the complete project. Previous isolated check failed (untrusted diagnostic data): "
            + json.dumps(output or result)[:2000]
        )
    return {
        "status": "blocked",
        "message": "The project did not pass its file and executable checks after one repair attempt. Files are saved; no GitHub push is claimed.",
    }
