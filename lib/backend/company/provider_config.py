"""Explicit CEO routing. Never silently substitute a different provider/model."""

import os


def configured_secret(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value.lower().startswith(("replace_", "your_", "test-only", "placeholder")):
        return ""
    return value


def ceo_configuration() -> dict:
    from developer_connections import connection

    from company.work_policy import WORK_SCOPE

    own = connection()
    if own:
        return {
            "provider": "developer",
            "model": own["model"],
            "configured": True,
            "model_env": "",
        }
    scope = WORK_SCOPE.get()
    if scope:
        return {
            "provider": "openrouter",
            "model": scope["model"],
            "configured": bool(configured_secret("OPENROUTER_API_KEY")),
            "model_env": "ARC_COMPANY_WORK_MODEL",
        }
    provider = os.getenv("ARC_CEO_PROVIDER", "google_ai_studio").strip().lower()
    if provider == "openrouter":
        model = (
            os.getenv("ARC_CEO_MODEL", "") or os.getenv("OPENROUTER_MAIN_MODEL", "")
        ).strip()
        return {
            "provider": provider,
            "model": model,
            "configured": bool(model and configured_secret("OPENROUTER_API_KEY")),
            "model_env": "ARC_CEO_MODEL",
        }
    if provider == "google_ai_studio":
        model = os.getenv("GEMINI_CEO_MODEL", "gemini-3.8-flash").strip()
        return {
            "provider": provider,
            "model": model,
            "configured": bool(
                model
                and (
                    configured_secret("GEMINI_API_KEY")
                    or configured_secret("GOOGLE_AI_API_KEY")
                )
            ),
            "model_env": "GEMINI_CEO_MODEL",
        }
    raise RuntimeError("ARC_CEO_PROVIDER must be google_ai_studio or openrouter")


def output_token_limit(setting: str, default: int = 1024) -> int:
    try:
        return min(max(int(os.getenv(setting, str(default))), 64), 4096)
    except ValueError:
        return default


def reasoning_options(setting: str, model: str | None = None) -> dict:
    """Use per-model reasoning support during autonomous work."""
    from developer_connections import connection

    from company.work_policy import WORK_SCOPE

    own = connection()
    if own:
        if own["provider"] != "openrouter":
            return {}
        from company.model_catalog import catalog

        entry = next(
            (m for m in catalog() if m.get("model_id") == (model or own["model"])), {}
        )
        return (
            {"reasoning": {"enabled": False}}
            if entry.get("reasoning_mandatory") is False
            else {}
        )
    scope = WORK_SCOPE.get()
    if scope:
        from company.model_catalog import catalog

        entry = next(
            (m for m in catalog() if m.get("model_id") == (model or scope["model"])), {}
        )
        return (
            {"reasoning": {"enabled": False}}
            if entry.get("reasoning_mandatory") is False
            else {}
        )
    value = os.getenv(setting, "").strip().lower()
    if not value:
        return {}
    if value == "off":
        return {"reasoning": {"enabled": False}}
    if value in {"minimal", "low", "medium", "high"}:
        return {"reasoning": {"effort": value}}
    raise ValueError(f"{setting} must be off, minimal, low, medium, or high")
