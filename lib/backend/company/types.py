import os
from dataclasses import dataclass
from typing import Literal

Provider = Literal["google_ai_studio", "openrouter"]


@dataclass(frozen=True)
class AgentProfile:
    slug: str
    display_name: str
    job_title: str
    department: str
    purpose: str
    provider: Provider
    model_env: str
    default_model: str
    reports_to: str | None
    tool_names: tuple[str, ...]
    instructions: str

    @property
    def model(self) -> str:
        if self.slug == "ceo":
            from company.provider_config import ceo_configuration

            return ceo_configuration()["model"]
        return os.getenv(self.model_env, self.default_model).strip()

    def public_dict(self) -> dict[str, object]:
        from company.provider_config import ceo_configuration

        ceo = ceo_configuration() if self.slug == "ceo" else None
        return {
            "id": self.slug,
            "name": self.display_name,
            "job_title": self.job_title,
            "department": self.department,
            "purpose": self.purpose,
            "provider": ceo["provider"] if ceo else self.provider,
            "model": self.model,
            "reports_to": self.reports_to,
            "tools": list(self.tool_names),
        }
