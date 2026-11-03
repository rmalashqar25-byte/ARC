"""Task-local autonomous access; never changes a founder's global approvals."""

import math
from contextvars import ContextVar

WORK_SCOPE = ContextVar("arc_work_scope", default=None)
LOCAL_TOOLS = frozenset(
    {
        "calculator",
        "finance_summary",
        "workspace_read",
        "workspace_search",
        "workspace_update",
        "draft_file",
        "terminal_run",
        "delegate_agent",
    }
)


def model_prices(entry):
    try:
        prices = tuple(
            float(entry[key])
            for key in ("input_price_per_million", "output_price_per_million")
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    return prices if all(math.isfinite(p) and p >= 0 for p in prices) else None


def allowed_work_model(entry, company):
    prices = model_prices(entry)
    if prices is None:
        return False
    if prices == (0, 0):
        return True
    limits = company.get("price_limits", {})
    if limits.get("model") != company["model"]:
        return False
    approved = model_prices(limits)
    return approved is not None and all(p <= cap for p, cap in zip(prices, approved))


def model_gate(model):
    scope = WORK_SCOPE.get()
    if not scope:
        return
    from company.model_catalog import catalog

    company = scope["database"].company(scope["actor"], scope["session"])
    if company["model"] != scope["model"]:
        raise ValueError(
            "Company model changed; restart this task with the current selection"
        )
    from developer_connections import connection

    own = connection()
    if own:
        if model != own["model"]:
            raise ValueError(
                "Developer model changed; save the current model in Company work"
            )
        if not scope.get("interactive"):
            scope["database"].reserve_call(scope["actor"], scope["session"])
        return
    entry = next((m for m in catalog() if m.get("model_id") == model), {})
    if not allowed_work_model(entry, company):
        raise ValueError(
            "This model needs pricing confirmation in the company work board"
        )
    if not scope.get("interactive"):
        scope["database"].reserve_call(scope["actor"], scope["session"])


def local_permission(actor, session, tool):
    scope = WORK_SCOPE.get()
    if not scope or scope["actor"] != actor or scope["session"] != session:
        return None
    if not scope["database"].company(actor, session)["enabled"]:
        return "deny"
    return "allow" if tool in LOCAL_TOOLS else "deny"
