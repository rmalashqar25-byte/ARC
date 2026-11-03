"""Private OpenRouter runtime for company leads and employees."""

import asyncio
import json
import os
from functools import lru_cache
from typing import Any

from agent_store import get_agent_store
from agent_tools import (
    dispatch_tool,
    make_tool_context,
    public_tool_catalog,
    tool_schemas,
)
from dotenv import load_dotenv
from openai import OpenAI

from company.collaboration import record_agent_report, record_delegation
from company.communication import protect_agent_text
from company.organization import get_profile, public_agent_catalog
from company.provider_config import output_token_limit, reasoning_options

load_dotenv()

MAX_AGENT_STEPS = 10
MAX_SESSION_MESSAGES = 60
MAX_SESSIONS = 500
MAX_DELEGATION_DEPTH = 2
_sessions: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
_session_locks: dict[tuple[str, str, str], asyncio.Lock] = {}


@lru_cache(maxsize=1)
def _openrouter_client() -> OpenAI:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        timeout=90.0,
        max_retries=2,
    )


def _trim_session(messages: list[dict[str, Any]]) -> None:
    if len(messages) > MAX_SESSION_MESSAGES:
        messages[:] = [messages[0], *messages[-(MAX_SESSION_MESSAGES - 1) :]]


def _content_as_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif hasattr(item, "text") and isinstance(item.text, str):
                parts.append(item.text)
        return "\n".join(parts)
    return str(content)


def _remove_oldest_session_if_needed() -> None:
    if len(_sessions) < MAX_SESSIONS:
        return
    oldest_key = next(iter(_sessions))
    _sessions.pop(oldest_key, None)
    _session_locks.pop(oldest_key, None)


def company_catalog() -> list[dict[str, Any]]:
    catalog = []
    for agent in public_agent_catalog():
        profile = get_profile(str(agent["id"]))
        catalog.append(
            {**agent, "tool_details": public_tool_catalog(profile.tool_names)}
        )
    return catalog


def agent_details(agent_id: str) -> dict[str, Any]:
    profile = get_profile(agent_id)
    return {
        **profile.public_dict(),
        "tools": public_tool_catalog(profile.tool_names),
        "publicly_callable": profile.slug == "ceo",
    }


async def run_company_agent(
    agent_id: str,
    prompt: str,
    session_id: str,
    delegation_depth: int = 1,
    actor_id: str = "local",
    requested_by: str | None = None,
    group_id: str | None = None,
) -> dict[str, Any]:
    profile = get_profile(agent_id)
    if profile.provider != "openrouter":
        raise ValueError("The CEO must be invoked through the Google AI Studio runtime")
    from company.team import assignment, get_team

    team = get_team(actor_id, session_id)
    hired_agent = assignment(actor_id, session_id, profile.slug)
    if team["mode"] in {"manual", "ceo"} and hired_agent is None:
        raise ValueError(f"{profile.job_title} has not been hired for this project")
    from developer_connections import completion_options, connection, model_client

    own = connection(actor_id)
    active_model = (
        own["model"]
        if own
        else (hired_agent["model"] if hired_agent else profile.model)
    )
    if own and not own.get("supports_tools", True):
        raise ValueError(
            "Enable tool calling for a compatible model in Developer settings"
        )

    clean_prompt = (prompt or "").strip()
    clean_session_id = (session_id or "").strip()
    clean_actor_id = (actor_id or "").strip()
    if not clean_prompt:
        raise ValueError("Prompt cannot be empty")
    if len(clean_prompt) > 8_000:
        raise ValueError("Prompt cannot exceed 8000 characters")
    if not clean_session_id or len(clean_session_id) > 64:
        raise ValueError("session_id must contain between 1 and 64 characters")
    if not clean_actor_id or len(clean_actor_id) > 128:
        raise ValueError("actor_id must contain between 1 and 128 characters")
    if not 1 <= delegation_depth <= MAX_DELEGATION_DEPTH:
        raise ValueError("Invalid company delegation depth")
    manager_id = (requested_by or "").strip().lower()
    if not manager_id or profile.reports_to != manager_id:
        raise ValueError(
            f"Agent '{profile.slug}' may be invoked only by direct manager "
            f"'{profile.reports_to}'"
        )
    group = record_delegation(
        actor_id=clean_actor_id,
        session_id=clean_session_id,
        sender_id=manager_id,
        recipient_id=profile.slug,
        task=clean_prompt,
        group_id=group_id,
    )
    active_group_id = str(group["group_id"])

    from company.work_policy import WORK_SCOPE

    scope = WORK_SCOPE.get()
    conversation_session = (
        clean_session_id + ":" + scope["task_id"]
        if scope and scope.get("task_id")
        else clean_session_id
    )
    key = (clean_actor_id, profile.slug, conversation_session)
    lock = _session_locks.setdefault(key, asyncio.Lock())
    active_tools = profile.tool_names
    if delegation_depth >= MAX_DELEGATION_DEPTH:
        active_tools = tuple(name for name in active_tools if name != "delegate_agent")

    async with lock:
        messages = _sessions.get(key)
        if messages is None:
            _remove_oldest_session_if_needed()
            persisted = await asyncio.to_thread(
                get_agent_store().load_session,
                clean_actor_id,
                profile.slug,
                conversation_session,
            )
            messages = persisted or [
                {"role": "system", "content": profile.instructions}
            ]
            _sessions[key] = messages

        if hired_agent:
            messages[0] = {
                "role": "system",
                "content": (
                    profile.instructions
                    + "\nYour marketplace identity is "
                    + hired_agent["name"]
                    + ". Work only with hired roles in this project team: "
                    + json.dumps(team)
                ),
            }

        messages.append({"role": "user", "content": clean_prompt})
        _trim_session(messages)
        await asyncio.to_thread(
            get_agent_store().save_session,
            clean_actor_id,
            profile.slug,
            conversation_session,
            messages,
        )

        for _ in range(MAX_AGENT_STEPS):
            from company.work_policy import model_gate

            model_gate(active_model)
            client = model_client(own) if own else _openrouter_client()
            if scope:
                client = client.with_options(max_retries=0)
            try:
                completion = await asyncio.to_thread(
                    client.chat.completions.create,
                    model=active_model,
                    **(
                        completion_options(
                            own, output_token_limit("ARC_AGENT_MAX_OUTPUT_TOKENS", 4096)
                        )
                        if own
                        else {
                            "max_tokens": output_token_limit(
                                "ARC_AGENT_MAX_OUTPUT_TOKENS", 4096
                            )
                        }
                    ),
                    messages=messages,
                    tools=tool_schemas(active_tools),
                    tool_choice="auto",
                    extra_body=reasoning_options("ARC_AGENT_REASONING", active_model),
                )
            finally:
                if own:
                    client.close()
            message = completion.choices[0].message
            message_payload = message.model_dump(exclude_none=True)
            if isinstance(message_payload.get("content"), str):
                message_payload["content"] = protect_agent_text(
                    message_payload["content"]
                )
            if message_payload.get("tool_calls"):
                message_payload["tool_calls"] = message_payload["tool_calls"][:8]
            messages.append(message_payload)

            if not message.tool_calls:
                report = (
                    protect_agent_text(_content_as_text(message.content))
                    or "No report returned."
                )
                _trim_session(messages)
                await asyncio.to_thread(
                    get_agent_store().save_session,
                    clean_actor_id,
                    profile.slug,
                    conversation_session,
                    messages,
                )
                record_agent_report(
                    actor_id=clean_actor_id,
                    session_id=clean_session_id,
                    sender_id=profile.slug,
                    recipient_id=manager_id,
                    content=report,
                    group_id=active_group_id,
                )
                return {
                    "agent_id": profile.slug,
                    "agent": hired_agent["name"]
                    if hired_agent
                    else profile.display_name,
                    "job_title": profile.job_title,
                    "provider": profile.provider,
                    "model": active_model,
                    "message": report,
                    "group_id": active_group_id,
                    "pending_approvals": [],
                }

            pending_approvals: list[dict[str, Any]] = []
            tool_results: list[dict[str, Any]] = []
            context = make_tool_context(
                profile.slug,
                clean_session_id,
                delegation_depth,
                actor_id=clean_actor_id,
                company_group_id=active_group_id,
            )
            for tool_call in message.tool_calls[:8]:
                tool_name = tool_call.function.name
                try:
                    arguments = json.loads(tool_call.function.arguments or "{}")
                    if not isinstance(arguments, dict):
                        raise ValueError("Tool arguments must be a JSON object")
                    result, pending = await dispatch_tool(
                        active_tools,
                        tool_name,
                        arguments,
                        context,
                    )
                except (json.JSONDecodeError, TypeError, ValueError) as error:
                    result = {
                        "status": "failed",
                        "tool": tool_name,
                        "error": str(error),
                    }
                    pending = None

                tool_results.append(result)
                if pending is not None:
                    pending_approvals.append(pending)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(
                            result,
                            ensure_ascii=False,
                            default=str,
                        ),
                    }
                )

            _trim_session(messages)
            await asyncio.to_thread(
                get_agent_store().save_session,
                clean_actor_id,
                profile.slug,
                conversation_session,
                messages,
            )
            if pending_approvals:
                report = protect_agent_text(_content_as_text(message.content)) or (
                    "One or more actions require the user's approval."
                )
                record_agent_report(
                    actor_id=clean_actor_id,
                    session_id=clean_session_id,
                    sender_id=profile.slug,
                    recipient_id=manager_id,
                    content=report,
                    group_id=active_group_id,
                )
                return {
                    "agent_id": profile.slug,
                    "agent": profile.display_name,
                    "job_title": profile.job_title,
                    "provider": profile.provider,
                    "model": active_model,
                    "message": report,
                    "group_id": active_group_id,
                    "pending_approvals": pending_approvals,
                    "tool_results": tool_results,
                }

    report = "Work is incomplete: the agent reached its step limit. Any file changes are saved, but completion is not verified. Review the task or retry."
    record_agent_report(
        actor_id=clean_actor_id,
        session_id=clean_session_id,
        sender_id=profile.slug,
        recipient_id=manager_id,
        content=report,
        group_id=active_group_id,
    )
    return {
        "agent_id": profile.slug,
        "agent": profile.display_name,
        "job_title": profile.job_title,
        "provider": profile.provider,
        "model": active_model,
        "group_id": active_group_id,
        "status": "blocked",
        "reason": "step_limit",
        "message": report,
        "pending_approvals": [],
    }


def clear_agent_session(
    agent_id: str,
    session_id: str,
    actor_id: str = "local",
) -> bool:
    profile = get_profile(agent_id)
    key = (actor_id, profile.slug, session_id)
    removed_memory = _sessions.pop(key, None) is not None
    _session_locks.pop(key, None)
    removed_store = get_agent_store().delete_session(
        actor_id,
        profile.slug,
        session_id,
    )
    return removed_memory or removed_store


def clear_company_session(session_id: str, actor_id: str = "local") -> bool:
    from company.ceo import clear_ceo_session
    from company.collaboration import clear_company_collaboration
    from company.organization import PROFILES

    removed = clear_ceo_session(session_id, actor_id)
    removed = (
        get_agent_store().delete_session(actor_id, "project_team", session_id)
        or removed
    )
    for profile in PROFILES.values():
        if profile.slug != "ceo":
            removed = clear_agent_session(profile.slug, session_id, actor_id) or removed
    removed = clear_company_collaboration(actor_id, session_id) or removed
    return removed
