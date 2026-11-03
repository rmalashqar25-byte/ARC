"""Human membership and capacity without exposing internal conversations."""

from agent_store import get_agent_store

from company.organization import get_profile
from company.work_policy import WORK_SCOPE


def resource_key(actor, person):
    return (
        "talent:" + person["talent_id"]
        if person.get("talent_id")
        else actor + ":" + person["id"]
    )


def human_offer(
    database, actor, session, person, *, title, description, manager="ceo", dedupe=None
):
    profile = get_profile(manager)
    if manager != "ceo" and profile.reports_to != "ceo":
        raise ValueError("Choose the CEO or a department manager for this person")
    store = get_agent_store()
    existing = next(
        (
            g
            for g in store.list_company_groups(actor, session)
            if g["director_id"] == manager
        ),
        None,
    )
    group, _ = (
        (existing, False)
        if existing
        else store.get_or_create_company_group(
            actor_id=actor,
            session_id=session,
            name="Company office"
            if manager == "ceo"
            else profile.department + " group",
            director_id=manager,
            objective="Assigned company work",
        )
    )
    capacity = person.get("job_capacity", 3)
    if person.get("talent_id"):
        live = next(
            (
                p
                for p in store.list_talent_profiles(actor)
                if p["id"] == person["talent_id"]
            ),
            None,
        )
        if not live or live.get("availability") == "unavailable":
            raise ValueError("This person is not accepting new jobs")
        capacity = min(capacity, live.get("job_capacity", 3))
    scope = WORK_SCOPE.get()
    task = database.create(
        actor,
        session,
        title=title,
        description=description,
        kind="human",
        assignee=person["id"],
        manager=manager,
        dedupe=dedupe,
        group_id=group["group_id"],
        capacity_key=resource_key(actor, person),
        human_capacity=capacity,
        parent=scope.get("task_id") if scope else None,
    )
    store.add_company_group_member(
        actor_id=actor,
        session_id=session,
        group_id=group["group_id"],
        agent_id="human:" + person["id"],
        membership_role="employee",
        added_by=manager,
        display_name=person["name"],
    )
    return task
