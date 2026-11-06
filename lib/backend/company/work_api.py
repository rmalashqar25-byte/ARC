"""Founder work board and capability-scoped human delivery portal."""

from agent_store import get_agent_store
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from company.organization import PROFILES, get_profile
from company.work_policy import model_prices
from company.work_runtime import work_event, work_models


class WorkSettings(BaseModel):
    enabled: bool
    model: str = Field(default="", max_length=200)
    confirm_local_autonomy: bool = False
    confirm_paid_model: bool = False


class WorkCreate(BaseModel):
    requires_check: bool = False
    title: str = Field(min_length=1, max_length=140)
    description: str = Field(min_length=1, max_length=8000)
    kind: str = Field(default="agent", pattern="^(agent|human)$")
    assignee: str = Field(default="ceo", min_length=1, max_length=100)
    manager: str = Field(default="ceo", min_length=1, max_length=100)


class Delivery(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)


class Review(BaseModel):
    decision: str = Field(pattern="^(accepted|changes_requested)$")
    feedback: str = Field(default="", max_length=8000)


def public_task(task, worker=False):
    excluded = {"actor", "recipient_actor", "lease", "due", "capacity_key"}
    if worker:
        excluded |= {"session", "parent", "attempts"}
    return {k: v for k, v in task.items() if k not in excluded}


def build_work_router(access_dependency):
    router = APIRouter()

    def database():
        db = get_agent_store().work_store
        if db is None:
            raise HTTPException(503, "Company work is not ready. Try again shortly.")
        return db

    def session_id(value):
        if not 1 <= len(value) <= 64:
            raise HTTPException(422, "Invalid project")
        return value

    def task_for(db, actor, project_id, task_id):
        try:
            return db.get(actor, project_id, task_id)
        except ValueError:
            raise HTTPException(404, "Task not found") from None

    @router.get("/company/sessions/{project_id}/work")
    async def board(
        project_id: str,
        request: Request,
        refresh: bool = False,
        actor: str = Depends(access_dependency),
    ):
        from developer_connections import connection

        if refresh and not connection():
            from company.model_catalog import refresh_catalog

            await refresh_catalog()
        db = database()
        worker = getattr(request.app.state, "company_worker", None)
        return {
            **db.company(actor, session_id(project_id)),
            "check_interval_seconds": 5,
            "free_only": False,
            "worker_running": bool(worker and not worker.last_error),
            "last_check": worker.last_check if worker else None,
            "managers": [
                {"id": p.slug, "name": p.display_name}
                for p in PROFILES.values()
                if p.slug == "ceo" or p.reports_to == "ceo"
            ],
            "tasks": [public_task(t) for t in db.list(actor, project_id)],
            "models": [
                {
                    k: m.get(k)
                    for k in (
                        "model_id",
                        "name",
                        "input_price_per_million",
                        "output_price_per_million",
                        "developer_connection",
                    )
                }
                for m in work_models()
            ],
            "employees": [
                dict(
                    e,
                    remaining_capacity=max(
                        0,
                        e.get("job_capacity", 3)
                        - db.human_load(
                            "talent:" + e["talent_id"]
                            if e.get("talent_id")
                            else actor + ":" + e["id"]
                        ),
                    ),
                )
                for e in get_agent_store().list_human_employees(actor)
                if e.get("session_id", "") in {"", project_id}
            ],
        }

    @router.post("/company/work/pause-all")
    def pause_all(actor: str = Depends(access_dependency)):
        db = get_agent_store().work_store
        if db:
            db.pause_actor(actor)
        return {"paused": True}

    @router.put("/company/sessions/{project_id}/work")
    def configure(
        project_id: str, request: WorkSettings, actor: str = Depends(access_dependency)
    ):
        if request.enabled and not request.confirm_local_autonomy:
            raise HTTPException(400, "Confirm automatic local project work first")
        selected = next(
            (m for m in work_models() if m["model_id"] == request.model), None
        )
        if (request.enabled or request.model) and not selected:
            raise HTTPException(400, "Choose an available compatible model")
        prices = model_prices(selected or {})
        paid = prices is not None and prices != (0, 0)
        existing = database().company(actor, session_id(project_id))
        if (
            paid
            and not request.confirm_paid_model
            and (request.enabled or request.model != existing["model"])
        ):
            raise HTTPException(
                400, "Confirm this model’s pricing before starting automatic work"
            )
        limits = (
            {
                "model": request.model,
                "input_price_per_million": selected["input_price_per_million"],
                "output_price_per_million": selected["output_price_per_million"],
            }
            if request.confirm_paid_model and selected
            else {}
        )
        if (
            not request.enabled
            and request.model == existing["model"]
            and not request.confirm_paid_model
        ):
            limits = existing.get("price_limits", {})
        if request.enabled:
            from company.team import get_team, save_team

            if get_team(actor, project_id)["mode"] == "undecided":
                save_team(actor, project_id, "ceo", [])
        configured = database().configure(
            actor,
            session_id(project_id),
            request.enabled,
            request.model,
            price_limits=limits,
        )
        if bool(existing["enabled"]) != request.enabled:
            get_agent_store().append_company_event(
                actor_id=actor,
                session_id=project_id,
                group_id=None,
                sender_id="ceo",
                recipient_id="user",
                event_type="company_resumed" if request.enabled else "company_paused",
                content="Automatic company work is running. I’ll report results or blockers here."
                if request.enabled
                else "Automatic company work is paused. Saved tasks remain available; resume them in Company work.",
                metadata={},
            )
        return configured

    @router.post("/company/sessions/{project_id}/work/tasks", status_code=201)
    def create(
        project_id: str, request: WorkCreate, actor: str = Depends(access_dependency)
    ):
        session_id(project_id)
        if not request.title.strip() or not request.description.strip():
            raise HTTPException(422, "Describe the work first")
        try:
            get_profile(request.manager)
            if request.kind == "agent":
                get_profile(request.assignee)
                task = database().create(actor, project_id, **request.model_dump())
            else:
                employees = get_agent_store().list_human_employees(actor)
                person = next(
                    (
                        e
                        for e in employees
                        if e["id"] == request.assignee
                        and e.get("session_id", project_id) in {"", project_id}
                    ),
                    None,
                )
                if person is None:
                    raise ValueError("Human employee not found")
                from company.human_work import human_offer

                task = human_offer(
                    database(),
                    actor,
                    project_id,
                    person,
                    title=request.title,
                    description=request.description,
                    manager=request.manager,
                )
            work_event(
                task,
                "work_offered" if request.kind == "human" else "work_queued",
                f"{request.title}: {'Awaiting the person’s acceptance' if request.kind == 'human' else 'Queued for company work'}",
            )
            return public_task(task)
        except ValueError as error:
            raise HTTPException(400, str(error)) from None

    @router.post("/company/sessions/{project_id}/work/tasks/{task_id}/retry")
    def retry(project_id: str, task_id: str, actor: str = Depends(access_dependency)):
        db = database()
        task = task_for(db, actor, project_id, task_id)
        if task["kind"] == "human":
            raise HTTPException(400, "Use the human review workflow")
        try:
            return public_task(
                db.update(
                    actor,
                    project_id,
                    task_id,
                    status="queued",
                    feedback="",
                    allowed={"blocked"},
                    reset_attempts=True,
                )
            )
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @router.post("/company/sessions/{project_id}/work/invites/{employee}")
    def invite(project_id: str, employee: str, actor: str = Depends(access_dependency)):
        if not any(
            e["id"] == employee and e.get("session_id", "") in {"", project_id}
            for e in get_agent_store().list_human_employees(actor)
        ):
            raise HTTPException(404, "Employee not found")
        return {
            "token": database().invitation(actor, session_id(project_id), employee),
            "expires_in_days": 7,
        }

    @router.delete("/company/sessions/{project_id}/work/invites/{employee}")
    def revoke(project_id: str, employee: str, actor: str = Depends(access_dependency)):
        database().revoke(actor, project_id, employee)
        return {"revoked": True}

    @router.post("/company/sessions/{project_id}/work/tasks/{task_id}/review")
    def review(
        project_id: str,
        task_id: str,
        request: Review,
        actor: str = Depends(access_dependency),
    ):
        task = task_for(database(), actor, project_id, task_id)
        if task["kind"] != "human":
            raise HTTPException(400, "Only human submissions can be reviewed here")
        try:
            return public_task(
                database().update(
                    actor,
                    project_id,
                    task_id,
                    status=request.decision,
                    feedback=request.feedback,
                    allowed={"submitted"},
                )
            )
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    def worker(x_arc_worker: str = Header(default="")):
        try:
            return database().worker_access(x_arc_worker)
        except PermissionError as error:
            raise HTTPException(401, str(error)) from None

    def worker_task(access, task_id):
        task = task_for(database(), access["actor"], access["session"], task_id)
        if task["kind"] != "human" or task["assignee"] != access["employee"]:
            raise HTTPException(404, "Task not found")
        return task

    @router.get("/work/tasks")
    def worker_tasks(access=Depends(worker)):
        tasks = database().list(access["actor"], access["session"])
        own = [
            t
            for t in tasks
            if t["kind"] == "human" and t["assignee"] == access["employee"]
        ]
        person = next(
            (
                p
                for p in get_agent_store().list_human_employees(access["actor"])
                if p["id"] == access["employee"]
            ),
            None,
        )
        if person is None:
            raise HTTPException(401, "This employee workspace is no longer available")
        from company.human_work import resource_key

        groups = []
        for gid in dict.fromkeys(t.get("group_id") for t in own if t.get("group_id")):
            group = get_agent_store().get_company_group(
                access["actor"], access["session"], gid
            )
            if group:
                groups.append(
                    {
                        "id": gid,
                        "name": group["name"],
                        "manager_name": get_profile(group["director_id"]).display_name,
                    }
                )
        return {
            "tasks": [public_task(t, True) for t in own],
            "groups": groups,
            "person": {
                "name": person["name"],
                "job_capacity": person.get("job_capacity", 3),
                "active_jobs": database().human_load(
                    resource_key(access["actor"], person)
                ),
            },
        }

    @router.post("/work/tasks/{task_id}/decline")
    def decline(task_id: str, access=Depends(worker)):
        worker_task(access, task_id)
        try:
            return public_task(
                database().update(
                    access["actor"],
                    access["session"],
                    task_id,
                    status="declined",
                    allowed={"offered"},
                ),
                True,
            )
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @router.post("/work/tasks/{task_id}/accept")
    def accept(task_id: str, access=Depends(worker)):
        worker_task(access, task_id)
        try:
            return public_task(
                database().update(
                    access["actor"],
                    access["session"],
                    task_id,
                    status="in_progress",
                    allowed={"offered"},
                ),
                True,
            )
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @router.post("/work/tasks/{task_id}/submit")
    def submit(task_id: str, request: Delivery, access=Depends(worker)):
        task = worker_task(access, task_id)
        if not request.content.strip():
            raise HTTPException(422, "Add your work before submitting")
        try:
            updated = database().update(
                access["actor"],
                access["session"],
                task_id,
                status="submitted",
                result=request.content.strip(),
                allowed={"in_progress", "changes_requested"},
            )
            database().create(
                access["actor"],
                access["session"],
                title="Review: " + task["title"],
                description="Review the submitted human work against its brief.",
                kind="review",
                assignee=task["manager"],
                manager=task["manager"],
                parent=task_id,
                dedupe=f"review:{task_id}:{updated['updated']}",
            )
            work_event(
                task,
                "human_submission",
                f"Human work submitted for {task['manager'].replace('_', ' ')}: {task['title']}",
            )
            return public_task(updated, True)
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    return router
