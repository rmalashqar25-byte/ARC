"""Durable, read-only collaboration timeline for Arc Company sessions."""

from typing import Any

from agent_store import get_agent_store

from company.communication import protect_agent_text
from company.organization import allowed_delegate_targets, get_profile

MAX_EVENT_CONTENT = 12_000


def _clean_content(value: str, field: str) -> str:
    content = (value or "").strip()
    if field != "User message":
        content = protect_agent_text(content)
    if not content:
        raise ValueError(f"{field} cannot be empty")
    if len(content) > MAX_EVENT_CONTENT:
        content = content[:MAX_EVENT_CONTENT] + "…"
    return content


def _agent_metadata(agent_id: str) -> dict[str, str]:
    profile = get_profile(agent_id)
    return {
        "agent_id": profile.slug,
        "agent_name": profile.display_name,
        "job_title": profile.job_title,
        "department": profile.department,
    }


def record_user_request(actor_id: str, session_id: str, content: str) -> dict[str, Any]:
    return get_agent_store().append_company_event(
        actor_id=actor_id,
        session_id=session_id,
        group_id=None,
        sender_id="user",
        recipient_id="ceo",
        event_type="user_message",
        content=_clean_content(content, "User message"),
        metadata={"read_only_internal_agents": True},
    )


def record_ceo_response(actor_id: str, session_id: str, content: str) -> dict[str, Any]:
    return get_agent_store().append_company_event(
        actor_id=actor_id,
        session_id=session_id,
        group_id=None,
        sender_id="ceo",
        recipient_id="user",
        event_type="ceo_response",
        content=_clean_content(content, "CEO response"),
        metadata=_agent_metadata("ceo"),
    )


def ensure_director_group(
    actor_id: str,
    session_id: str,
    director_id: str,
    objective: str,
) -> dict[str, Any]:
    normalized_director = (director_id or "").strip().lower()
    if normalized_director not in allowed_delegate_targets("ceo"):
        raise ValueError("The CEO may create groups only with direct-report directors")
    director = get_profile(normalized_director)
    store = get_agent_store()
    group, created = store.get_or_create_company_group(
        actor_id=actor_id,
        session_id=session_id,
        name=f"{director.department} group",
        director_id=director.slug,
        objective=_clean_content(objective, "Group objective"),
    )
    store.add_company_group_member(
        actor_id=actor_id,
        session_id=session_id,
        group_id=group["group_id"],
        agent_id="ceo",
        membership_role="executive",
        added_by="system",
    )
    store.add_company_group_member(
        actor_id=actor_id,
        session_id=session_id,
        group_id=group["group_id"],
        agent_id=director.slug,
        membership_role="director",
        added_by="ceo",
    )
    if created:
        store.append_company_event(
            actor_id=actor_id,
            session_id=session_id,
            group_id=group["group_id"],
            sender_id="ceo",
            recipient_id=director.slug,
            event_type="group_created",
            content=f"Created {group['name']} for: {group['objective']}",
            metadata={
                "director": _agent_metadata(director.slug),
                "user_can_post": False,
            },
        )
    return group


def record_delegation(
    *,
    actor_id: str,
    session_id: str,
    sender_id: str,
    recipient_id: str,
    task: str,
    group_id: str | None = None,
) -> dict[str, Any]:
    sender = (sender_id or "").strip().lower()
    recipient = (recipient_id or "").strip().lower()
    if recipient not in allowed_delegate_targets(sender):
        allowed = allowed_delegate_targets(sender)
        raise ValueError(
            f"Agent '{sender}' may delegate only to direct reports: "
            + (", ".join(allowed) if allowed else "none")
        )
    clean_task = _clean_content(task, "Delegated task")
    if sender == "ceo":
        group = ensure_director_group(actor_id, session_id, recipient, clean_task)
    else:
        if not group_id:
            raise ValueError("Director-to-employee delegation requires a company group")
        store = get_agent_store()
        group = store.get_company_group(actor_id, session_id, group_id)
        if group is None:
            raise ValueError("Company group was not found for this user session")
        if group["director_id"] != sender:
            raise ValueError("Only this group's director may add or task employees")
        added = store.add_company_group_member(
            actor_id=actor_id,
            session_id=session_id,
            group_id=group_id,
            agent_id=recipient,
            membership_role="employee",
            added_by=sender,
        )
        if added:
            store.append_company_event(
                actor_id=actor_id,
                session_id=session_id,
                group_id=group_id,
                sender_id=sender,
                recipient_id=recipient,
                event_type="member_added",
                content=f"{get_profile(recipient).display_name} joined {group['name']}.",
                metadata={"member": _agent_metadata(recipient)},
            )

    get_agent_store().append_company_event(
        actor_id=actor_id,
        session_id=session_id,
        group_id=group["group_id"],
        sender_id=sender,
        recipient_id=recipient,
        event_type="task_delegated",
        content=clean_task,
        metadata={
            "sender": _agent_metadata(sender),
            "recipient": _agent_metadata(recipient),
        },
    )
    return group


def record_agent_report(
    *,
    actor_id: str,
    session_id: str,
    sender_id: str,
    recipient_id: str,
    content: str,
    group_id: str,
) -> dict[str, Any]:
    sender = (sender_id or "").strip().lower()
    recipient = (recipient_id or "").strip().lower()
    sender_profile = get_profile(sender)
    if sender_profile.reports_to != recipient:
        raise ValueError("An internal agent may report only to its direct manager")
    group = get_agent_store().get_company_group(actor_id, session_id, group_id)
    if group is None:
        raise ValueError("Company group was not found for this user session")
    if sender_profile.reports_to == "ceo":
        valid_group = group["director_id"] == sender
    else:
        valid_group = group["director_id"] == recipient
    if not valid_group:
        raise ValueError("The report does not belong to this company group")
    return get_agent_store().append_company_event(
        actor_id=actor_id,
        session_id=session_id,
        group_id=group_id,
        sender_id=sender,
        recipient_id=recipient,
        event_type="agent_report",
        content=_clean_content(content, "Agent report"),
        metadata={
            "sender": _agent_metadata(sender),
            "recipient": _agent_metadata(recipient),
        },
    )


def company_groups(actor_id: str, session_id: str) -> list[dict[str, Any]]:
    return get_agent_store().list_company_groups(actor_id, session_id)


def company_events(
    actor_id: str,
    session_id: str,
    *,
    after_id: int = 0,
    limit: int = 200,
) -> list[dict[str, Any]]:
    return get_agent_store().list_company_events(
        actor_id,
        session_id,
        after_id=after_id,
        limit=limit,
    )


def clear_company_collaboration(actor_id: str, session_id: str) -> bool:
    return get_agent_store().delete_company_session_state(actor_id, session_id)
