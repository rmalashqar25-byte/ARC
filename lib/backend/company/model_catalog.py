"""Model-level facts from OpenRouter, with capability-based task suggestions."""

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import httpx

SNAPSHOT = Path(__file__).with_name("model_catalog.json")
_catalog = None
_refresh_lock = asyncio.Lock()


def normalize_models(models, checked_on=None):
    checked_on = checked_on or datetime.now(timezone.utc).date().isoformat()
    result = []
    for model in models:
        model_id = model.get("id", "")
        if not model_id or "/" not in model_id:
            continue
        architecture = model.get("architecture") or {}
        inputs = architecture.get("input_modalities") or ["text"]
        outputs = architecture.get("output_modalities") or ["text"]
        params = model.get("supported_parameters") or []
        tools = "tools" in params
        reasoning = any(p in params for p in ("reasoning", "reasoning_effort"))
        context = int(model.get("context_length") or 0)
        description = str(model.get("description", "")).lower()
        categories = []
        if "text" in outputs:
            categories.extend(["operations", "marketing"])
            if reasoning or context >= 32768:
                categories.extend(["research", "finance", "legal"])
            if tools or any(
                w in description for w in ("coding", "programming", "code generation")
            ):
                categories.append("it")
            if "image" in inputs or "image" in outputs:
                categories.append("design")
        if any(m in outputs for m in ("image", "audio", "video")):
            categories.extend(["design", "marketing"])
        if not categories:
            categories = ["research"]
        categories = list(dict.fromkeys(categories))
        focus = []
        for terms, label in [
            (("coding", "programming", "code generation"), "coding workflows"),
            (("reasoning",), "analytical reasoning"),
            (("multilingual",), "multilingual tasks"),
            (("mathematical", "mathematics"), "math problem solving"),
            (("creative writing",), "creative writing"),
            (("low-latency", "low latency"), "latency-sensitive work"),
        ]:
            if any(term in description for term in terms):
                focus.append(label)
        facts = ["Provider focus: " + ", ".join(focus[:2]) + "."] if focus else []
        facts.append(f"Accepts {', '.join(inputs)}; produces {', '.join(outputs)}.")
        if context:
            facts.append(f"{context:,}-token context window.")
        facts.append(
            "Supports connected tool calls."
            if tools
            else "No tool-calling support listed."
        )
        if reasoning:
            facts.append("Offers reasoning controls for analysis tasks.")
        pricing = model.get("pricing") or {}

        def cost(key):
            try:
                value = float(pricing[key])
                return round(value * 1_000_000, 6) if value >= 0 else None
            except (KeyError, TypeError, ValueError):
                return None

        role_id = (
            "cto"
            if "it" in categories
            else "market_researcher"
            if "research" in categories
            else "content_marketer"
        )
        result.append(
            {
                "id": model_id,
                "model_id": model_id,
                "name": str(model.get("name") or model_id).split(": ", 1)[-1],
                "provider": model_id.split("/", 1)[0],
                "summary": " ".join(facts),
                "categories": categories,
                "context_length": context,
                "input_modalities": inputs,
                "output_modalities": outputs,
                "supports_tools": tools,
                "supports_reasoning": reasoning,
                "reasoning_mandatory": (model.get("reasoning") or {}).get("mandatory"),
                "agent_compatible": tools and "text" in outputs,
                "input_price_per_million": cost("prompt"),
                "output_price_per_million": cost("completion"),
                "source_url": "https://openrouter.ai/" + quote(model_id, safe="/:-_."),
                "checked_on": checked_on,
                "created": int(model.get("created") or 0),
                "role_id": role_id,
                "role": "Choose a company role",
                "price": 0,
                "considerations": "Task matches are suggestions based on listed capabilities, not benchmark rankings. Research needs connected sources and fact checking. Token rates may exclude image, search, and other provider charges.",
            }
        )
    return result


def catalog():
    global _catalog
    if _catalog is None:
        _catalog = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    return _catalog


_last_refresh_attempt = float("-inf")


async def refresh_catalog():
    global _catalog, _last_refresh_attempt
    async with _refresh_lock:
        # A refresh is shared across all actors, including provider failures.
        now = time.monotonic()
        if now - _last_refresh_attempt < 60:
            return False
        _last_refresh_attempt = now
        try:
            async with httpx.AsyncClient(
                timeout=15.0, follow_redirects=False
            ) as client:
                response = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    params={"output_modalities": "all"},
                )
                response.raise_for_status()
                models = normalize_models(response.json()["data"])
            if models:
                _catalog = models
            return True
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return False
