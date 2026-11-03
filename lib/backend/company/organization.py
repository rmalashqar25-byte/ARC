"""Authoritative ARC Company organization chart and delegation policy."""

from company.ceo import CEO_PROFILE
from company.finance import FINANCE_PROFILES
from company.it import IT_PROFILES
from company.legal import LEGAL_PROFILES
from company.management import MANAGEMENT_PROFILES
from company.marketing import MARKETING_PROFILES
from company.types import AgentProfile

PROFILES: dict[str, AgentProfile] = {"ceo": CEO_PROFILE}
for group in (
    IT_PROFILES,
    MANAGEMENT_PROFILES,
    MARKETING_PROFILES,
    FINANCE_PROFILES,
    LEGAL_PROFILES,
):
    overlap = PROFILES.keys() & group.keys()
    if overlap:
        raise RuntimeError(f"Duplicate company agent IDs: {sorted(overlap)}")
    PROFILES.update(group)


def get_profile(slug: str) -> AgentProfile:
    normalized = (slug or "").strip().lower()
    try:
        return PROFILES[normalized]
    except KeyError as error:
        allowed = ", ".join(PROFILES)
        raise ValueError(
            f"Unknown company agent '{slug}'. Choose one of: {allowed}"
        ) from error


def allowed_delegate_targets(manager_slug: str) -> tuple[str, ...]:
    normalized = (manager_slug or "").strip().lower()
    if normalized not in PROFILES:
        return ()
    return tuple(
        profile.slug
        for profile in PROFILES.values()
        if profile.reports_to == normalized
    )


def public_agent_catalog() -> list[dict[str, object]]:
    return [profile.public_dict() for profile in PROFILES.values()]


def organization_tree() -> dict[str, object]:
    def node(slug: str) -> dict[str, object]:
        profile = get_profile(slug)
        return {
            "id": profile.slug,
            "name": profile.display_name,
            "job_title": profile.job_title,
            "provider": profile.provider,
            "reports": [node(child) for child in allowed_delegate_targets(slug)],
        }

    return node("ceo")
