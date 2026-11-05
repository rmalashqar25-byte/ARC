"""Thread-safe company state with optional recovery and transient approvals."""

import time
import uuid
from copy import deepcopy
from functools import lru_cache, wraps
from threading import RLock

VALID_PERMISSION_MODES = {"allow", "ask", "deny"}


class StateCapacityError(RuntimeError):
    """Finite RAM budget reached; refuse new state rather than evict permissions."""


def durable(method):
    @wraps(method)
    def saved(self, *args, **kwargs):
        with self._lock:
            result = method(self, *args, **kwargs)
            if self.work_store:
                self.work_store.save_state(self.company_snapshot())
            return result

    return saved


class AgentStore:
    def __init__(self):
        self._lock = RLock()
        self.permissions = {}
        self.approval_modes = {}
        self.human_employees = {}
        self.human_tasks = {}
        self.talent_profiles = {}
        self.pending = {}
        self.sessions = {}
        self.groups = {}
        self.members = {}
        self.events = []
        self.audit = []
        self.jobs = {}
        self.oauth = {}
        self.connections = {}
        self._event_id = 0
        self._audit_id = 0
        self.work_store = None

    def company_snapshot(self):
        return {
            "sessions": [[list(key), value] for key, value in self.sessions.items()],
            "members": [[list(key), value] for key, value in self.members.items()],
            "groups": self.groups,
            "events": self.events,
            "event_id": self._event_id,
            "human_employees": self.human_employees,
            "human_tasks": self.human_tasks,
            "talent_profiles": self.talent_profiles,
            "github_connections": [
                [list(key), value] for key, value in self.connections.items()
            ],
            "restrictions": [
                [
                    list(key),
                    dict(
                        value,
                        mode="deny" if value["mode"] == "deny" else "ask",
                        scope={},
                        remaining_uses=0,
                    ),
                ]
                for key, value in self.permissions.items()
            ],
        }

    def bind_work_store(self, database):
        with self._lock:
            state = database.load_state()
            if state:
                self.sessions = {tuple(key): value for key, value in state["sessions"]}
                self.members = {tuple(key): value for key, value in state["members"]}
                for name in (
                    "groups",
                    "events",
                    "human_employees",
                    "human_tasks",
                    "talent_profiles",
                ):
                    setattr(self, name, state[name])
                self._event_id = state["event_id"]
                self.permissions = {
                    tuple(key): value for key, value in state.get("restrictions", [])
                }
                self.connections = {
                    tuple(key): value
                    for key, value in state.get("github_connections", [])
                }
            self.work_store = database
            database.save_state(self.company_snapshot())

    def _reserve(self, collection, key, maximum=1000):
        if key not in collection and len(collection) >= maximum:
            raise StateCapacityError(
                "Temporary state capacity reached; retry after cleanup or server restart"
            )

    def _reserve_nested(self, collection, actor_id, key, maximum=100):
        self._reserve(collection, actor_id, 250)
        self._reserve(collection.get(actor_id, {}), key, maximum)

    def get_approval_mode(self, actor_id):
        with self._lock:
            return self.approval_modes.get(actor_id, "ask")

    def set_approval_mode(self, actor_id, mode):
        if mode not in {"ask", "allow"}:
            raise ValueError("Approval mode must be ask or allow")
        with self._lock:
            self._reserve(self.approval_modes, actor_id)
            self.approval_modes[actor_id] = mode
            return mode

    @durable
    def add_human_employee(self, actor_id, name, role, **details):
        with self._lock:
            employee = dict(
                deepcopy(details), id=str(uuid.uuid4()), name=name, role=role
            )
            self._reserve_nested(self.human_employees, actor_id, employee["id"])
            self.human_employees.setdefault(actor_id, {})[employee["id"]] = employee
            return deepcopy(employee)

    def list_human_employees(self, actor_id):
        with self._lock:
            return deepcopy(list(self.human_employees.get(actor_id, {}).values()))

    @durable
    def save_talent_profile(self, actor_id, profile):
        with self._lock:
            previous = self.talent_profiles.get(actor_id, {})
            item = dict(
                deepcopy(profile),
                id=previous.get("id", str(uuid.uuid4())),
                updated_at=time.time(),
            )
            self._reserve(self.talent_profiles, actor_id, 500)
            self.talent_profiles[actor_id] = item
            return dict(deepcopy(item), is_mine=True)

    def get_talent_profile(self, actor_id):
        with self._lock:
            item = self.talent_profiles.get(actor_id)
            return dict(deepcopy(item), is_mine=True) if item else None

    def list_talent_profiles(self, actor_id):
        with self._lock:
            return [
                dict(deepcopy(item), is_mine=owner == actor_id)
                for owner, item in self.talent_profiles.items()
                if item["published"]
            ]

    @durable
    def delete_talent_profile(self, actor_id):
        with self._lock:
            return self.talent_profiles.pop(actor_id, None) is not None

    @durable
    def draft_talent_brief(self, actor_id, profile_id, session_id, description):
        with self._lock:
            profile = next(
                (
                    p
                    for p in self.talent_profiles.values()
                    if p["id"] == profile_id and p["published"]
                ),
                None,
            )
            if profile is None:
                raise ValueError("This profile is no longer listed")
            if profile["availability"] == "unavailable":
                raise ValueError("This person is not available for new work")
            employee_id = "talent:" + profile_id
            self._reserve_nested(self.human_employees, actor_id, employee_id)
            self.human_employees.setdefault(actor_id, {})[employee_id] = {
                "id": employee_id,
                "name": profile["name"],
                "role": profile["role"],
            }
            return self.assign_human_task(
                actor_id, session_id, employee_id, description
            )

    @durable
    def assign_human_task(self, actor_id, session_id, employee_id, description):
        with self._lock:
            employee = self.human_employees.get(actor_id, {}).get(employee_id)
            if employee is None or (
                employee.get("session_id") and employee["session_id"] != session_id
            ):
                raise ValueError("Human employee not found for this project")
            task = {
                "id": str(uuid.uuid4()),
                "session_id": session_id,
                "employee_id": employee_id,
                "employee_name": employee["name"],
                "description": description,
                "status": "draft_assignment",
                "created_at": time.time(),
            }
            self._reserve_nested(self.human_tasks, actor_id, task["id"], 200)
            self.human_tasks.setdefault(actor_id, {})[task["id"]] = task
            return deepcopy(task)

    def list_human_tasks(self, actor_id, session_id):
        with self._lock:
            return deepcopy(
                [
                    task
                    for task in self.human_tasks.get(actor_id, {}).values()
                    if task["session_id"] == session_id
                ]
            )

    def get_permission(self, actor_id, role, session_id, tool_name):
        with self._lock:
            key = (actor_id, role, session_id, tool_name)
            item = self.permissions.get(key)
            if (
                item
                and item["mode"] == "allow"
                and (item["expires_at"] <= time.time() or item["remaining_uses"] <= 0)
            ):
                # Retain an ask tombstone: an exhausted grant must not fall back
                # to the actor's broader global allow setting.
                item.update(mode="ask", scope={}, remaining_uses=0)
            elif item and item["expires_at"] <= time.time():
                item.update(mode="ask", scope={}, remaining_uses=0)
            return deepcopy(item)

    def consume_permission(
        self, actor_id, role, session_id, tool_name, arguments=None, scope_check=None
    ):
        with self._lock:
            item = self.get_permission(actor_id, role, session_id, tool_name)
            if (
                not item
                or item["mode"] != "allow"
                or (scope_check and not scope_check(item["scope"]))
            ):
                return None
            self.permissions[(actor_id, role, session_id, tool_name)][
                "remaining_uses"
            ] -= 1
            return item

    @durable
    def set_permission(
        self, actor_id, role, session_id, tool_name, mode, scope, expires_at, max_uses
    ):
        if mode not in VALID_PERMISSION_MODES or max_uses < 0:
            raise ValueError("Invalid permission mode or use count")
        with self._lock:
            self._reserve(
                self.permissions, (actor_id, role, session_id, tool_name), 4000
            )
            self.permissions[(actor_id, role, session_id, tool_name)] = {
                "mode": mode,
                "scope": deepcopy(scope),
                "expires_at": expires_at,
                "remaining_uses": max_uses,
                "updated_at": time.time(),
            }

    @durable
    def delete_permission(self, actor_id, role, session_id, tool_name):
        with self._lock:
            return (
                self.permissions.pop((actor_id, role, session_id, tool_name), None)
                is not None
            )

    def list_permissions(self, actor_id):
        with self._lock:
            result = []
            for actor, role, session, tool in list(self.permissions):
                if actor != actor_id:
                    continue
                item = self.get_permission(actor, role, session, tool)
                if item:
                    result.append(
                        dict(item, role=role, session_id=session, tool_name=tool)
                    )
            return sorted(result, key=lambda x: (x["role"], x["tool_name"]))

    def create_pending_action(self, action):
        with self._lock:
            self.pending = {
                key: value
                for key, value in self.pending.items()
                if value["status"] == "pending" and value["expires_at"] > time.time()
            }
            key = action["approval_id"]
            self._reserve(self.pending, key, 500)
            if (
                sum(
                    v.get("actor_id") == action.get("actor_id")
                    for v in self.pending.values()
                )
                >= 100
            ):
                raise StateCapacityError(
                    "Too many pending approvals for this session owner"
                )
            if key in self.pending:
                raise ValueError("Duplicate approval")
            self.pending[key] = dict(
                deepcopy(action), status="pending", resolved_at=None
            )

    def get_pending_action(self, approval_id):
        with self._lock:
            item = self.pending.get(approval_id)
            if (
                item
                and item["expires_at"] <= time.time()
                and item["status"] == "pending"
            ):
                item.update(status="expired", resolved_at=time.time())
            return deepcopy(item) if item and item["status"] == "pending" else None

    def list_pending_actions(self, actor_id):
        with self._lock:
            result = []
            for approval_id in list(self.pending):
                item = self.get_pending_action(approval_id)
                if item and item["actor_id"] == actor_id:
                    result.append(
                        {
                            "approval_id": approval_id,
                            "session_id": item["session_id"],
                            "role": item["role"],
                            "tool": item["tool_name"],
                            "arguments": deepcopy(item["arguments"]),
                            "expires_at": item["expires_at"],
                        }
                    )
            return result

    def resolve_pending_action(self, approval_id, status):
        if status not in {"approved", "denied"}:
            raise ValueError("Approval status must be approved or denied")
        with self._lock:
            if not self.get_pending_action(approval_id):
                return False
            self.pending[approval_id].update(status=status, resolved_at=time.time())
            return True

    def append_audit(self, record):
        with self._lock:
            self._audit_id += 1
            self.audit.append(
                dict(
                    deepcopy(record),
                    id=self._audit_id,
                    timestamp=record["timestamp_epoch"],
                )
            )
            del self.audit[:-2000]

    def get_audit(self, actor_id, session_id, limit):
        with self._lock:
            return deepcopy(
                [
                    r
                    for r in self.audit
                    if r["actor_id"] == actor_id
                    and (not session_id or r["session_id"] == session_id)
                ][-max(1, min(limit, 500)) :]
            )

    def load_session(self, actor_id, role, session_id):
        with self._lock:
            return deepcopy(self.sessions.get((actor_id, role, session_id)))

    @durable
    def save_session(self, actor_id, role, session_id, messages):
        with self._lock:
            self._reserve(self.sessions, (actor_id, role, session_id), 1000)
            import json

            if len(json.dumps(messages, default=str).encode("utf-8")) > 256_000:
                raise StateCapacityError(
                    "Conversation memory limit reached; start a new conversation"
                )
            self.sessions[(actor_id, role, session_id)] = deepcopy(messages)

    @durable
    def delete_session(self, actor_id, role, session_id):
        with self._lock:
            return self.sessions.pop((actor_id, role, session_id), None) is not None

    @durable
    def get_or_create_company_group(
        self, *, actor_id, session_id, name, director_id, objective
    ):
        with self._lock:
            for group in self.groups.values():
                if (group["actor_id"], group["session_id"], group["director_id"]) == (
                    actor_id,
                    session_id,
                    director_id,
                ):
                    if objective and objective != group["objective"]:
                        group.update(
                            objective=objective, status="active", updated_at=time.time()
                        )
                    return deepcopy(group), False
            now = time.time()
            group = dict(
                group_id="group_" + uuid.uuid4().hex,
                actor_id=actor_id,
                session_id=session_id,
                name=name,
                director_id=director_id,
                objective=objective,
                status="active",
                created_at=now,
                updated_at=now,
            )
            self._reserve(self.groups, group["group_id"])
            self.groups[group["group_id"]] = group
            return deepcopy(group), True

    def get_company_group(self, actor_id, session_id, group_id):
        with self._lock:
            group = self.groups.get(group_id)
            return (
                deepcopy(group)
                if group
                and (group["actor_id"], group["session_id"]) == (actor_id, session_id)
                else None
            )

    @durable
    def add_company_group_member(
        self,
        *,
        actor_id,
        session_id,
        group_id,
        agent_id,
        membership_role,
        added_by,
        display_name=None,
    ):
        if membership_role not in {"executive", "director", "employee"}:
            raise ValueError("Invalid company group membership role")
        with self._lock:
            if not self.get_company_group(actor_id, session_id, group_id):
                raise ValueError("Company group was not found for this user session")
            key = (group_id, agent_id)
            created = key not in self.members
            self._reserve(self.members, key, 5000)
            self.members[key] = dict(
                agent_id=agent_id,
                membership_role=membership_role,
                added_by=added_by,
                joined_at=self.members.get(key, {}).get("joined_at", time.time()),
                display_name=display_name,
            )
            return created

    @durable
    def append_company_event(
        self,
        *,
        actor_id,
        session_id,
        group_id,
        sender_id,
        recipient_id,
        event_type,
        content,
        metadata=None,
    ):
        with self._lock:
            if group_id is not None and not self.get_company_group(
                actor_id, session_id, group_id
            ):
                raise ValueError("Company group was not found for this user session")
            self._event_id += 1
            item = dict(
                id=self._event_id,
                session_id=session_id,
                group_id=group_id,
                sender_id=sender_id,
                recipient_id=recipient_id,
                event_type=event_type,
                content=content,
                metadata=deepcopy(metadata or {}),
                created_at=time.time(),
            )
            self.events.append((actor_id, item))
            del self.events[:-4000]
            return deepcopy(item)

    def list_company_groups(self, actor_id, session_id):
        with self._lock:
            result = []
            for group in self.groups.values():
                if (group["actor_id"], group["session_id"]) == (actor_id, session_id):
                    item = deepcopy(group)
                    item.pop("actor_id")
                    item["members"] = [
                        deepcopy(member)
                        for (gid, _), member in self.members.items()
                        if gid == group["group_id"]
                    ]
                    result.append(item)
            return sorted(result, key=lambda x: (x["created_at"], x["group_id"]))

    def list_company_events(self, actor_id, session_id, *, after_id=0, limit=200):
        with self._lock:
            return deepcopy(
                [
                    event
                    for actor, event in self.events
                    if actor == actor_id
                    and event["session_id"] == session_id
                    and event["id"] > max(int(after_id), 0)
                ][: min(max(int(limit), 1), 500)]
            )

    @durable
    def delete_company_session_state(self, actor_id, session_id):
        with self._lock:
            if self.work_store:
                self.work_store.delete_company(actor_id, session_id)
            self.sessions = {
                key: value
                for key, value in self.sessions.items()
                if not (
                    key[0] == actor_id
                    and (key[2] == session_id or key[2].startswith(session_id + ":"))
                )
            }
            # A deleted project must never retain executable approvals or grants.
            self.pending = {
                key: item
                for key, item in self.pending.items()
                if (item.get("actor_id"), item.get("session_id"))
                != (actor_id, session_id)
            }
            self.permissions = {
                key: item
                for key, item in self.permissions.items()
                if (key[0], key[2]) != (actor_id, session_id)
            }
            self.jobs = {
                key: item
                for key, item in self.jobs.items()
                if (item["actor_id"], item["session_id"]) != (actor_id, session_id)
            }
            employees = self.human_employees.get(actor_id, {})
            for key in list(employees):
                if employees[key].get("session_id") == session_id:
                    del employees[key]
            tasks = self.human_tasks.get(actor_id, {})
            removed_tasks = [
                task_id
                for task_id, task in tasks.items()
                if task["session_id"] == session_id
            ]
            for task_id in removed_tasks:
                del tasks[task_id]
            ids = {
                gid
                for gid, g in self.groups.items()
                if (g["actor_id"], g["session_id"]) == (actor_id, session_id)
            }
            old_count = len(self.events)
            self.events = [
                (a, e)
                for a, e in self.events
                if (a, e["session_id"]) != (actor_id, session_id)
            ]
            for gid in ids:
                del self.groups[gid]
            self.members = {k: v for k, v in self.members.items() if k[0] not in ids}
            return bool(ids) or old_count != len(self.events) or bool(removed_tasks)

    def create_publish_job(self, job):
        with self._lock:
            if job["job_id"] in self.jobs:
                raise ValueError("Duplicate publish job")
            self._reserve(self.jobs, job["job_id"], 500)
            self.jobs[job["job_id"]] = dict(
                deepcopy(job),
                status="queued",
                created_at=time.time(),
                updated_at=time.time(),
                error_message=None,
                published_commit=None,
            )

    def list_publish_jobs(self, actor_id, limit=50):
        with self._lock:
            jobs = [
                deepcopy(j) for j in self.jobs.values() if j["actor_id"] == actor_id
            ]
            for job in jobs:
                job.pop("actor_id")
            return sorted(jobs, key=lambda x: x["created_at"], reverse=True)[
                : min(max(int(limit), 1), 100)
            ]

    def get_publish_job(self, actor_id, job_id):
        with self._lock:
            job = self.jobs.get(job_id)
            return deepcopy(job) if job and job["actor_id"] == actor_id else None

    def transition_publish_job(
        self,
        actor_id,
        job_id,
        expected_statuses,
        status,
        *,
        error_message=None,
        published_commit=None,
    ):
        valid = {"queued", "running", "published", "failed", "cancelled"}
        if (
            status not in valid
            or not expected_statuses
            or not expected_statuses <= valid
        ):
            raise ValueError("Invalid publish-job status transition")
        with self._lock:
            job = self.jobs.get(job_id)
            if (
                not job
                or job["actor_id"] != actor_id
                or job["status"] not in expected_statuses
            ):
                return False
            job.update(
                status=status,
                updated_at=time.time(),
                error_message=error_message,
                published_commit=published_commit,
            )
            return True

    def create_github_oauth_state(self, state_digest, actor_id, expires_at):
        with self._lock:
            self.oauth = {k: v for k, v in self.oauth.items() if v[1] > time.time()}
            if state_digest in self.oauth:
                raise ValueError("Duplicate OAuth state")
            self._reserve(self.oauth, state_digest, 500)
            self.oauth[state_digest] = (actor_id, expires_at)

    def consume_github_oauth_state(self, state_digest):
        with self._lock:
            item = self.oauth.pop(state_digest, None)
            return item[0] if item and item[1] > time.time() else None

    @durable
    def save_github_connection(
        self,
        *,
        actor_id,
        installation_id,
        account_login,
        account_type,
        github_user_id,
        github_user_login,
    ):
        with self._lock:
            self._reserve(self.connections, (actor_id, installation_id), 1000)
            self.connections[(actor_id, installation_id)] = dict(
                installation_id=installation_id,
                account_login=account_login,
                account_type=account_type,
                github_user_id=github_user_id,
                github_user_login=github_user_login,
                updated_at=time.time(),
            )

    def list_github_connections(self, actor_id):
        with self._lock:
            return sorted(
                [
                    deepcopy(c)
                    for (a, _), c in self.connections.items()
                    if a == actor_id
                ],
                key=lambda x: x["account_login"],
            )

    @durable
    def delete_github_connection(self, actor_id, installation_id):
        with self._lock:
            return self.connections.pop((actor_id, installation_id), None) is not None

    def ping(self):
        return True


@lru_cache(maxsize=1)
def get_agent_store():
    return AgentStore()
