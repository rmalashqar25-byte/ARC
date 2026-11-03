"""Bounded human recommendations; offers require the person's acceptance."""

from agent_store import get_agent_store


def human_candidates(actor, session, prompt):
    store = get_agent_store()
    people = [
        dict(p, source="employee")
        for p in store.list_human_employees(actor)
        if p.get("session_id", "") in {"", session}
    ]
    people += [dict(p, source="talent") for p in store.list_talent_profiles(actor)]
    words = set(prompt.lower().split())
    from company.human_work import resource_key

    for person in people:
        key = (
            "talent:" + person["id"]
            if person["source"] == "talent"
            else resource_key(actor, person)
        )
        active = store.work_store.human_load(key) if store.work_store else 0
        person["remaining_capacity"] = max(0, person.get("job_capacity", 3) - active)
    people = [
        p
        for p in people
        if p.get("availability", "available") != "unavailable"
        and p["remaining_capacity"] > 0
    ]
    people.sort(
        key=lambda p: len(
            words.intersection(
                (
                    p.get("role", "")
                    + " "
                    + p.get("summary", "")
                    + " "
                    + " ".join(p.get("skills", []))
                )
                .lower()
                .split()
            )
        ),
        reverse=True,
    )
    keys = {
        "id",
        "name",
        "role",
        "summary",
        "skills",
        "availability",
        "rate",
        "pricing",
        "source",
        "job_capacity",
        "remaining_capacity",
    }
    return [{k: v for k, v in p.items() if k in keys} for p in people[:12]]


def prepare_human_offers(actor, session, proposed, candidates):
    from company.organization import get_profile
    from company.work_runtime import work_event

    store = get_agent_store()
    db = store.work_store
    if (
        not db
        or not db.company(actor, session)["enabled"]
        or not isinstance(proposed, list)
    ):
        return []
    indexed = {p["source"] + ":" + p["id"]: p for p in candidates}
    result = []
    for item in proposed[:4]:
        if not isinstance(item, dict):
            continue
        person = indexed.get(str(item.get("person", "")))
        description = str(item.get("task", "")).strip()[:8000]
        if not person or not description:
            continue
        manager = str(item.get("manager", "ceo"))
        try:
            get_profile(manager)
        except ValueError:
            continue
        employee_id = person["id"]
        if person["source"] == "talent":
            existing = next(
                (
                    p
                    for p in store.list_human_employees(actor)
                    if p.get("talent_id") == person["id"]
                    and p.get("session_id") == session
                ),
                None,
            )
            employee = existing or store.add_human_employee(
                actor,
                person["name"],
                person["role"],
                session_id=session,
                talent_id=person["id"],
                summary=person.get("summary", ""),
                skills=person.get("skills", []),
                rate=person.get("rate", 0),
                pricing=person.get("pricing", "hour"),
                availability=person.get("availability", "available"),
                job_capacity=person.get("job_capacity", 3),
            )
            employee_id = employee["id"]
        from company.human_work import human_offer

        employee = next(
            (p for p in store.list_human_employees(actor) if p["id"] == employee_id),
            None,
        )
        if not employee:
            continue
        try:
            task = human_offer(
                db,
                actor,
                session,
                employee,
                title="Proposed human assignment: " + person["role"],
                description=description,
                manager=manager,
                dedupe="human:" + employee_id + ":" + description,
            )
        except ValueError:
            continue
        # Dedupe prevents repeated plans from creating another assignment or message.
        if not any(
            e.get("metadata", {}).get("work_task_id") == task["id"]
            for e in store.list_company_events(actor, session, limit=500)
        ):
            work_event(
                task,
                "human_offer",
                f"Proposed {person['name']} for {person['role']}. The person must accept the task and agree to any paid terms before work begins.",
            )
        result.append(
            {"id": task["id"], "person": person["name"], "status": task["status"]}
        )
    return result
