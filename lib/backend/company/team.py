"""Project-scoped hiring choices and explicit real-model configuration."""

import json
import os
from pathlib import Path

from agent_store import get_agent_store

CATALOG = json.loads(
    Path(__file__).with_name("marketplace.json").read_text(encoding="utf-8")
)


def marketplace():
    from developer_connections import connection, model_entry

    from company.model_catalog import catalog

    own = connection()
    if own:
        return [model_entry(own)]
    connected = bool(os.getenv("OPENROUTER_API_KEY", "").strip())
    return [
        dict(item, configured=connected and item["agent_compatible"])
        for item in catalog()
    ]


def _hiring_catalog():
    from developer_connections import connection

    if connection():
        return {item["id"]: item for item in marketplace()}
    # Keep old session assignments readable, without showing provider personas as models.
    legacy = [
        dict(
            item,
            configured=bool(
                os.getenv(item["model_env"], "").strip()
                and os.getenv("OPENROUTER_API_KEY", "").strip()
            ),
        )
        for item in CATALOG
    ]
    return {item["id"]: item for item in [*marketplace(), *legacy]}


def planning_marketplace(prompt):
    candidates = [m for m in marketplace() if m["configured"]]
    from company.work_policy import WORK_SCOPE, allowed_work_model

    scope = WORK_SCOPE.get()
    from developer_connections import connection

    if scope and not connection():
        company = scope["database"].company(scope["actor"], scope["session"])
        candidates = [m for m in candidates if allowed_work_model(m, company)]
    words = set(prompt.lower().split())
    candidates.sort(
        key=lambda m: (len(words.intersection(m["categories"])), m["created"]),
        reverse=True,
    )
    return [
        {k: m[k] for k in ("id", "name", "categories", "summary")}
        for m in candidates[:60]
    ]


def get_team(actor_id, session_id):
    team = get_agent_store().load_session(actor_id, "project_team", session_id) or {
        "mode": "undecided",
        "members": [],
    }
    from developer_connections import connection

    own = connection(actor_id)
    if own:
        team = dict(
            team, members=[dict(m, agent_id=own["model"]) for m in team["members"]]
        )
    return team


def save_team(actor_id, session_id, mode, members):
    from company.organization import get_profile

    if mode not in {"manual", "ceo"}:
        raise ValueError("Choose your team yourself or let the CEO choose")
    catalog = _hiring_catalog()
    if len(members) > 24:
        raise ValueError("A project can have at most 24 assignments")
    checked, roles = [], set()
    for member in members:
        item = catalog.get(member.get("agent_id"))
        role = member.get("role_id", "")
        if not item or role == "ceo" or get_profile(role).provider != "openrouter":
            raise ValueError("Invalid marketplace agent or company role")
        if role in roles:
            raise ValueError("Choose one agent per company role")
        if not item["configured"]:
            raise ValueError(
                f"{item['name']} needs its matching model configured before hiring"
            )
        roles.add(role)
        checked.append({"agent_id": item["id"], "role_id": role})
    team = {"mode": mode, "members": checked}
    get_agent_store().save_session(actor_id, "project_team", session_id, team)
    return team


def assignment(actor_id, session_id, role_id):
    from developer_connections import connection, model_entry

    own = connection(actor_id)
    team = get_team(actor_id, session_id)
    member = next((m for m in team["members"] if m["role_id"] == role_id), None)
    if member is None:
        return None
    if own:
        return dict(model_entry(own), model=own["model"])
    item = _hiring_catalog().get(member["agent_id"])
    if item is None:
        raise RuntimeError(
            "This model is no longer in the catalog. Choose a replacement."
        )
    model = item.get("model_id") or os.getenv(item["model_env"], "").strip()
    if not model or not os.getenv("OPENROUTER_API_KEY", "").strip():
        raise RuntimeError(f"{item['name']} matching model is no longer configured")
    return dict(item, model=model)
