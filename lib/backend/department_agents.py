"""Compatibility entry points; internal agents stay behind CEO delegation."""

from typing import Any

# Compatibility names for code that still imports the former flat module.
from company.runtime import agent_details as department_details
from company.runtime import clear_agent_session as _clear_company_agent_session
from company.runtime import company_catalog as department_catalog

__all__ = [
    "department_details",
    "department_catalog",
    "run_department_agent",
    "clear_department_session",
]


async def run_department_agent(
    department: str,
    prompt: str,
    session_id: str,
    delegation_depth: int = 0,
    actor_id: str = "local",
) -> dict[str, Any]:
    if (department or "").strip().lower() == "ceo":
        from company.ceo import run_ceo_agent

        return await run_ceo_agent(prompt, session_id, actor_id=actor_id)
    raise PermissionError(
        "Internal company agents cannot be called directly; send the request "
        "to the CEO and let the reporting hierarchy delegate it."
    )


def clear_department_session(
    department: str,
    session_id: str,
    actor_id: str = "local",
) -> bool:
    if (department or "").strip().lower() == "ceo":
        from company.ceo import clear_ceo_session

        return clear_ceo_session(session_id, actor_id)
    return _clear_company_agent_session(department, session_id, actor_id)
