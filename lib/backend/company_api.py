"""Temporary-session HTTP boundary for Arc Company."""

import asyncio
import json
import logging
from typing import Any, Callable, Literal

import httpx
from agent_store import get_agent_store
from agent_tools import (
    get_audit_events,
    permission_catalog,
    reset_tool_permission,
    resolve_pending_action,
    set_tool_permission,
)
from company.ceo import CeoProviderError, run_ceo_agent
from company.collaboration import company_events, company_groups
from company.organization import organization_tree
from company.provider_config import ceo_configuration
from company.runtime import (
    agent_details as company_agent_details,
)
from company.runtime import (
    clear_company_session,
    company_catalog,
)
from company.talent import example_profile
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from openai import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    RateLimitError,
)
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class CompanyAgentRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8_000)
    session_id: str = Field(min_length=1, max_length=64)


class ProjectTeamRequest(BaseModel):
    mode: Literal["manual", "ceo"]
    members: list[dict[str, str]] = Field(default_factory=list, max_length=24)


class CompanyApprovalDecision(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    approval_token: str = Field(min_length=20, max_length=200)
    approve: bool


class CompanyApprovalSettingDecision(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    approve: bool


class CompanyPermissionUpdate(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    mode: Literal["allow", "ask", "deny"]
    scope: dict[str, Any] = Field(default_factory=dict)
    duration_minutes: int = Field(default=30, ge=1, le=60)
    max_uses: int = Field(default=5, ge=1, le=20)
    confirm_automatic_access: bool = False


class CompanyApprovalPolicy(BaseModel):
    mode: Literal["ask", "allow"]
    confirm_automatic_access: bool = False


class HumanEmployeeCreate(BaseModel):
    job_capacity: int = Field(default=3, ge=0, le=20)
    name: str = Field(min_length=1, max_length=100)
    role: str = Field(min_length=1, max_length=100)
    summary: str = Field(default="", max_length=1200)
    skills: list[str] = Field(default_factory=list, max_length=12)
    department: str = Field(
        default="general",
        pattern=r"^(general|research|it|design|marketing|finance|legal|operations)$",
    )
    session_id: str = Field(default="", max_length=64)
    rate: float = Field(default=0, ge=0, le=100_000, allow_inf_nan=False)
    pricing: Literal["hour", "project", "volunteer"] = "hour"
    availability: Literal["available", "limited", "unavailable"] = "available"

    @field_validator("skills")
    @classmethod
    def validate_employee_skills(cls, values):
        if any(len(v.strip()) > 40 for v in values):
            raise ValueError("Each skill must be at most 40 characters")
        return list(dict.fromkeys(v.strip() for v in values if v.strip()))


class TalentProfileRequest(BaseModel):
    job_capacity: int = Field(default=3, ge=0, le=20)
    name: str = Field(min_length=1, max_length=100)
    role: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=20, max_length=1200)
    skills: list[str] = Field(default_factory=list, max_length=12)
    rate: float = Field(default=0, ge=0, le=100_000, allow_inf_nan=False)
    pricing: Literal["hour", "project", "volunteer"] = "hour"
    availability: Literal["available", "limited", "unavailable"] = "available"
    published: bool = True
    department: str = Field(
        default="general",
        pattern=r"^(general|research|it|design|marketing|finance|legal|operations)$",
    )

    @field_validator("name", "role", "summary", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("skills")
    @classmethod
    def clean_skills(cls, values):
        skills = list(dict.fromkeys(v.strip() for v in values if v.strip()))
        if any(len(v) > 40 for v in skills):
            raise ValueError("Each skill must be at most 40 characters")
        return skills


class TalentBriefRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=8000)


class HumanTaskCreate(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    employee_id: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=8_000)


def _translate_agent_error(error: Exception) -> None:
    if isinstance(error, HTTPException):
        raise error
    if isinstance(error, ValueError):
        raise HTTPException(status_code=400, detail=str(error)) from error
    if isinstance(error, AuthenticationError):
        raise HTTPException(
            status_code=401, detail="OpenRouter rejected the configured API key."
        ) from error
    if isinstance(error, RateLimitError):
        raise HTTPException(
            status_code=429,
            detail="OpenRouter rate limit or account credit limit was reached.",
        ) from error
    if isinstance(error, APIConnectionError):
        raise HTTPException(
            status_code=503, detail="Arc Company could not connect to OpenRouter."
        ) from error
    if isinstance(error, APIStatusError):
        raise HTTPException(
            status_code=502,
            detail=f"OpenRouter returned provider error {error.status_code}.",
        ) from error
    if isinstance(error, CeoProviderError):
        status_code = error.status_code
        if status_code in {401, 403}:
            public_status = 401
        elif status_code in {402, 429}:
            public_status = status_code
        else:
            public_status = 503
        raise HTTPException(status_code=public_status, detail=str(error)) from error
    if isinstance(error, httpx.HTTPError):
        raise HTTPException(
            status_code=503,
            detail="Arc Company could not connect to an AI provider.",
        ) from error
    if isinstance(error, RuntimeError):
        raise HTTPException(status_code=503, detail=str(error)) from error
    logger.exception("Arc Company agent request failed")
    raise HTTPException(
        status_code=502, detail="Arc Company agent request failed"
    ) from error


def build_company_router(
    access_dependency: Callable[..., str],
    run_rate_limiter: Callable[[str], None] | None = None,
) -> APIRouter:
    """Build the Arc Company router with injected access and rate-limit policies."""
    router = APIRouter(prefix="/company", tags=["Arc Company"])

    @router.get("/talent")
    def talent(actor_id: str = Depends(access_dependency)):
        store = get_agent_store()
        people = store.list_talent_profiles(actor_id)
        for person in people:
            active = (
                store.work_store.human_load("talent:" + person["id"])
                if store.work_store
                else 0
            )
            person["active_jobs"] = active
            person["remaining_capacity"] = max(
                0, person.get("job_capacity", 3) - active
            )
        return {
            "profiles": [
                *people,
                example_profile(),
            ]
        }

    @router.get("/talent/profile")
    def my_talent_profile(actor_id: str = Depends(access_dependency)):
        return {"profile": get_agent_store().get_talent_profile(actor_id)}

    @router.put("/talent/profile")
    def publish_talent_profile(
        request: TalentProfileRequest, actor_id: str = Depends(access_dependency)
    ):
        data = request.model_dump()
        if data["pricing"] == "volunteer":
            data["rate"] = 0
        return get_agent_store().save_talent_profile(actor_id, data)

    @router.delete("/talent/profile")
    def remove_talent_profile(actor_id: str = Depends(access_dependency)):
        return {"removed": get_agent_store().delete_talent_profile(actor_id)}

    @router.post("/talent/{profile_id}/briefs", status_code=201)
    def draft_talent_brief(
        profile_id: str,
        request: TalentBriefRequest,
        actor_id: str = Depends(access_dependency),
    ):
        if not request.description.strip():
            raise HTTPException(status_code=400, detail="Describe the work first")
        try:
            return get_agent_store().draft_talent_brief(
                actor_id, profile_id, request.session_id, request.description.strip()
            )
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.get("/marketplace")
    async def marketplace_catalog(
        refresh: bool = False, _: str = Depends(access_dependency)
    ):
        from company.model_catalog import refresh_catalog
        from company.team import marketplace
        from developer_connections import connection

        refreshed = await refresh_catalog() if refresh and not connection() else False
        agents = marketplace()
        return {
            "agents": agents,
            "count": len(agents),
            "source": "https://openrouter.ai/api/v1/models",
            "refreshed": refreshed,
        }

    @router.get("/sessions/{session_id}/team")
    def project_team(session_id: str, actor_id: str = Depends(access_dependency)):
        from company.team import get_team

        if not 1 <= len(session_id) <= 64:
            raise HTTPException(status_code=422, detail="Invalid session_id")
        return get_team(actor_id, session_id)

    @router.get("/sessions/{session_id}/memory")
    def project_memory(session_id: str, actor_id: str = Depends(access_dependency)):
        from company.project_memory import read

        if not 1 <= len(session_id) <= 64:
            raise HTTPException(status_code=422, detail="Invalid session_id")
        return {"name": "PROJECT_MEMORY.md", "content": read(actor_id, session_id)}

    @router.put("/sessions/{session_id}/team")
    def update_project_team(
        session_id: str,
        request: ProjectTeamRequest,
        actor_id: str = Depends(access_dependency),
    ):
        from company.team import save_team

        if not 1 <= len(session_id) <= 64:
            raise HTTPException(status_code=422, detail="Invalid session_id")
        try:
            return save_team(actor_id, session_id, request.mode, request.members)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @router.get("/catalog")
    def catalog(_: str = Depends(access_dependency)):
        ceo = ceo_configuration()
        status = "ready" if ceo["configured"] else "unavailable"
        return {
            "product": "Arc Company",
            "entry_point": {
                "agent_id": "ceo",
                "status": status,
                "run_endpoint": "/company/ceo/run",
            },
            "ceo": {
                "status": status,
                "agent_id": "ceo",
                "provider": ceo["provider"],
                "model": ceo["model"],
            },
            "agents": company_catalog(),
            "organization": organization_tree(),
            "publicly_callable_agents": ["ceo"],
            "collaboration": {
                "user_can_message": ["ceo"],
                "internal_agents_are_read_only": True,
                "groups_endpoint": "/company/sessions/{session_id}/groups",
                "events_endpoint": "/company/sessions/{session_id}/events",
                "stream_endpoint": "/company/sessions/{session_id}/stream",
            },
        }

    @router.get("/approval-policy")
    def approval_policy(actor_id: str = Depends(access_dependency)):
        return {"mode": get_agent_store().get_approval_mode(actor_id)}

    @router.put("/approval-policy")
    def update_approval_policy(
        request: CompanyApprovalPolicy,
        actor_id: str = Depends(access_dependency),
    ):
        if request.mode == "allow" and not request.confirm_automatic_access:
            raise HTTPException(
                status_code=400, detail="Confirm automatic access to all agent tools."
            )
        return {"mode": get_agent_store().set_approval_mode(actor_id, request.mode)}

    @router.get("/humans")
    def humans(
        session_id: str | None = Query(default=None, max_length=64),
        actor_id: str = Depends(access_dependency),
    ):
        employees = get_agent_store().list_human_employees(actor_id)
        if session_id:
            employees = [
                e
                for e in employees
                if not e.get("session_id") or e["session_id"] == session_id
            ]
        return {"employees": employees}

    @router.post("/humans", status_code=201)
    def add_human(
        request: HumanEmployeeCreate, actor_id: str = Depends(access_dependency)
    ):
        if not request.name.strip() or not request.role.strip():
            raise HTTPException(status_code=400, detail="Name and role cannot be blank")
        return get_agent_store().add_human_employee(
            actor_id,
            request.name.strip(),
            request.role.strip(),
            **dict(
                request.model_dump(exclude={"name", "role"}),
                rate=0 if request.pricing == "volunteer" else request.rate,
            ),
        )

    @router.get("/human-tasks")
    def human_tasks(
        session_id: str = Query(min_length=1, max_length=64),
        actor_id: str = Depends(access_dependency),
    ):
        return {"tasks": get_agent_store().list_human_tasks(actor_id, session_id)}

    @router.post("/human-tasks", status_code=201)
    def assign_human_task(
        request: HumanTaskCreate, actor_id: str = Depends(access_dependency)
    ):
        if not request.description.strip():
            raise HTTPException(status_code=400, detail="Task cannot be blank")
        try:
            return get_agent_store().assign_human_task(
                actor_id,
                request.session_id,
                request.employee_id,
                request.description.strip(),
            )
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.get("/sessions/{session_id}/groups")
    def session_groups(
        session_id: str,
        actor_id: str = Depends(access_dependency),
    ):
        if not 1 <= len(session_id) <= 64:
            raise HTTPException(status_code=422, detail="Invalid session_id")
        return {
            "session_id": session_id,
            "user_can_message": ["ceo"],
            "groups": company_groups(actor_id, session_id),
        }

    @router.get("/sessions/{session_id}/events")
    def session_events(
        session_id: str,
        after_id: int = Query(default=0, ge=0),
        limit: int = Query(default=200, ge=1, le=500),
        actor_id: str = Depends(access_dependency),
    ):
        if not 1 <= len(session_id) <= 64:
            raise HTTPException(status_code=422, detail="Invalid session_id")
        events = company_events(
            actor_id,
            session_id,
            after_id=after_id,
            limit=limit,
        )
        return {
            "session_id": session_id,
            "read_only": True,
            "events": events,
            "next_after_id": events[-1]["id"] if events else after_id,
        }

    @router.get("/sessions/{session_id}/stream")
    async def session_event_stream(
        request: Request,
        session_id: str,
        after_id: int = Query(default=0, ge=0),
        actor_id: str = Depends(access_dependency),
    ):
        if not 1 <= len(session_id) <= 64:
            raise HTTPException(status_code=422, detail="Invalid session_id")

        async def stream_events():
            cursor = after_id
            heartbeat_ticks = 0
            deadline = asyncio.get_running_loop().time() + 55
            yield "retry: 1500\n\n"
            while asyncio.get_running_loop().time() < deadline:
                if await request.is_disconnected():
                    break
                events = await asyncio.to_thread(
                    company_events,
                    actor_id,
                    session_id,
                    after_id=cursor,
                    limit=100,
                )
                if events:
                    for event in events:
                        cursor = int(event["id"])
                        payload = json.dumps(event, ensure_ascii=False, default=str)
                        yield f"id: {cursor}\nevent: company_event\ndata: {payload}\n\n"
                    heartbeat_ticks = 0
                else:
                    heartbeat_ticks += 1
                    if heartbeat_ticks >= 10:
                        yield ": keep-alive\n\n"
                        heartbeat_ticks = 0
                await asyncio.sleep(1)

        return StreamingResponse(
            stream_events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store, no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get("/agents/{department}")
    def get_agent_details(department: str, _: str = Depends(access_dependency)):
        try:
            return company_agent_details(department)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.post("/ceo/run")
    async def run_ceo(
        request: CompanyAgentRequest,
        actor_id: str = Depends(access_dependency),
    ):
        from company.work_policy import WORK_SCOPE

        database = get_agent_store().work_store
        company = database.company(actor_id, request.session_id) if database else {}
        scope_token = (
            WORK_SCOPE.set(
                {
                    "actor": actor_id,
                    "session": request.session_id,
                    "model": company["model"],
                    "database": database,
                    "interactive": True,
                }
            )
            if company.get("model")
            else None
        )
        try:
            if run_rate_limiter is not None:
                run_rate_limiter(actor_id)
            return await run_ceo_agent(
                prompt=request.prompt,
                session_id=request.session_id,
                actor_id=actor_id,
            )
        except Exception as error:
            _translate_agent_error(error)
        finally:
            if scope_token is not None:
                WORK_SCOPE.reset(scope_token)

    @router.post("/agents/{department}/run")
    async def run_agent(
        department: str,
        request: CompanyAgentRequest,
        actor_id: str = Depends(access_dependency),
    ):
        if department.strip().lower() != "ceo":
            raise HTTPException(
                status_code=403,
                detail=(
                    "Internal company agents cannot be called directly. "
                    "Send the request to /company/ceo/run."
                ),
            )
        return await run_ceo(request, actor_id)

    @router.delete("/agents/{department}/sessions/{session_id}")
    def clear_session(
        department: str,
        session_id: str,
        actor_id: str = Depends(access_dependency),
    ):
        if department.strip().lower() != "ceo":
            raise HTTPException(
                status_code=403,
                detail="Only the public CEO session can be managed directly.",
            )
        try:
            return {"cleared": clear_company_session(session_id, actor_id=actor_id)}
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.delete("/sessions/{session_id}")
    def clear_full_company_session(
        session_id: str,
        actor_id: str = Depends(access_dependency),
    ):
        return {"cleared": clear_company_session(session_id, actor_id=actor_id)}

    @router.post("/approvals/{approval_id}")
    async def decide_action(
        approval_id: str,
        decision: CompanyApprovalDecision,
        actor_id: str = Depends(access_dependency),
    ):
        try:
            return await resolve_pending_action(
                approval_id=approval_id,
                approval_token=decision.approval_token,
                session_id=decision.session_id,
                approve=decision.approve,
                actor_id=actor_id,
            )
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.get("/approval-requests")
    def approval_requests(actor_id: str = Depends(access_dependency)):
        return {"requests": get_agent_store().list_pending_actions(actor_id)}

    @router.post("/approval-requests/{approval_id}")
    async def decide_from_settings(
        approval_id: str,
        decision: CompanyApprovalSettingDecision,
        actor_id: str = Depends(access_dependency),
    ):
        try:
            return await resolve_pending_action(
                approval_id=approval_id,
                approval_token=None,
                session_id=decision.session_id,
                approve=decision.approve,
                actor_id=actor_id,
            )
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.get("/permissions")
    def permissions(
        session_id: str = Query(min_length=1, max_length=64),
        actor_id: str = Depends(access_dependency),
    ):
        return {"permissions": permission_catalog(actor_id, session_id)}

    @router.put("/permissions/{department}/{tool_name}")
    def update_permission(
        department: str,
        tool_name: str,
        request: CompanyPermissionUpdate,
        actor_id: str = Depends(access_dependency),
    ):
        if request.mode == "allow" and not request.confirm_automatic_access:
            raise HTTPException(
                status_code=400,
                detail="Set confirm_automatic_access=true after showing the exact scope to the user.",
            )
        try:
            return set_tool_permission(
                actor_id=actor_id,
                role=department,
                session_id=request.session_id,
                tool_name=tool_name,
                mode=request.mode,
                duration_minutes=request.duration_minutes,
                max_uses=request.max_uses,
                scope=request.scope,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @router.delete("/permissions/{department}/{tool_name}")
    def reset_permission(
        department: str,
        tool_name: str,
        session_id: str = Query(min_length=1, max_length=64),
        actor_id: str = Depends(access_dependency),
    ):
        try:
            return reset_tool_permission(actor_id, department, session_id, tool_name)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @router.get("/audit")
    def audit(
        session_id: str | None = Query(default=None, max_length=64),
        limit: int = Query(default=100, ge=1, le=500),
        actor_id: str = Depends(access_dependency),
    ):
        return {"events": get_audit_events(session_id, limit, actor_id)}

    @router.get("/publish-jobs")
    def publish_jobs(
        limit: int = Query(default=50, ge=1, le=100),
        actor_id: str = Depends(access_dependency),
    ):
        return {"jobs": get_agent_store().list_publish_jobs(actor_id, limit)}

    @router.get("/publish-jobs/{job_id}")
    def publish_job(job_id: str, actor_id: str = Depends(access_dependency)):
        job = get_agent_store().get_publish_job(actor_id, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Publish job was not found")
        return job

    @router.delete("/publish-jobs/{job_id}")
    def cancel_publish_job(job_id: str, actor_id: str = Depends(access_dependency)):
        cancelled = get_agent_store().transition_publish_job(
            actor_id,
            job_id,
            {"queued"},
            "cancelled",
        )
        if not cancelled:
            raise HTTPException(
                status_code=409,
                detail="Only a queued publish job can be cancelled",
            )
        return {"job_id": job_id, "status": "cancelled"}

    return router
