"""Private SQLite work queue, worker invitations, and company recovery state."""

import hashlib
import json
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class WorkStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS companies (
                    actor TEXT NOT NULL, session TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0,
                    model TEXT NOT NULL DEFAULT '', PRIMARY KEY(actor, session));
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, actor TEXT NOT NULL, session TEXT NOT NULL,
                    kind TEXT NOT NULL, assignee TEXT NOT NULL, manager TEXT NOT NULL,
                    status TEXT NOT NULL, due REAL NOT NULL, lease REAL NOT NULL DEFAULT 0,
                    attempts INTEGER NOT NULL DEFAULT 0, parent TEXT,
                    created REAL NOT NULL, updated REAL NOT NULL, body TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS task_queue ON tasks(status, due);
                CREATE INDEX IF NOT EXISTS company_tasks ON tasks(actor, session);
                CREATE TABLE IF NOT EXISTS invites (
                    digest TEXT PRIMARY KEY, actor TEXT NOT NULL, session TEXT NOT NULL,
                    employee TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS usage (
                    actor TEXT NOT NULL, session TEXT NOT NULL, day TEXT NOT NULL,
                    requests INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(actor, session, day));
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(companies)")}
            if "price_limits" not in columns:
                db.execute(
                    "ALTER TABLE companies ADD COLUMN price_limits TEXT NOT NULL DEFAULT '{}'"
                )
        self.path.chmod(0o600)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def save_state(self, state):
        with self.connection() as db:
            db.execute(
                "INSERT OR REPLACE INTO state VALUES (1, ?)", (json.dumps(state),)
            )

    def load_state(self):
        with self.connection() as db:
            row = db.execute("SELECT body FROM state WHERE id=1").fetchone()
        return json.loads(row["body"]) if row else None

    def company(self, actor, session):
        with self.connection() as db:
            row = db.execute(
                "SELECT enabled, model, price_limits FROM companies WHERE actor=? AND session=?",
                (actor, session),
            ).fetchone()
        result = (
            dict(row) if row else {"enabled": False, "model": "", "price_limits": "{}"}
        )
        result["price_limits"] = json.loads(result["price_limits"])
        return result

    def configure(self, actor, session, enabled, model="", price_limits=None):
        with self.connection() as db:
            db.execute(
                "INSERT INTO companies (actor,session,enabled,model,price_limits) VALUES (?,?,?,?,?) ON CONFLICT(actor,session) DO UPDATE SET enabled=excluded.enabled, model=excluded.model, price_limits=excluded.price_limits",
                (actor, session, int(enabled), model, json.dumps(price_limits or {})),
            )
        return self.company(actor, session)

    @staticmethod
    def unpack(row):
        data = dict(row)
        data.update(json.loads(data.pop("body")))
        return data

    def create(
        self,
        actor,
        session,
        *,
        title,
        description,
        kind="agent",
        assignee="ceo",
        manager="ceo",
        parent=None,
        recipient_actor=None,
        dedupe=None,
        requires_check=False,
        group_id=None,
        capacity_key=None,
        human_capacity=3,
    ):
        now = time.time()
        body = {
            "title": title,
            "description": description,
            "result": "",
            "feedback": "",
            "recipient_actor": recipient_actor,
            "requires_check": requires_check,
            "verified_check": False,
            "group_id": group_id,
            "capacity_key": capacity_key or actor + ":" + assignee,
        }
        task_id = "work_" + (
            hashlib.sha256(f"{actor}:{session}:{dedupe}".encode()).hexdigest()[:32]
            if dedupe
            else uuid.uuid4().hex
        )
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT * FROM tasks WHERE id=?", (task_id,)
            ).fetchone()
            if existing:
                return self.unpack(existing)
            if kind == "human":
                occupied = db.execute(
                    "SELECT COUNT(*) FROM tasks WHERE kind='human' AND json_extract(body,'$.capacity_key')=? AND status IN ('offered','in_progress','submitted','changes_requested')",
                    (body["capacity_key"],),
                ).fetchone()[0]
                if occupied >= human_capacity:
                    raise ValueError("This person has no remaining job capacity")
            if (
                db.execute(
                    "SELECT COUNT(*) FROM tasks WHERE actor=? AND status NOT IN ('completed','accepted','declined')",
                    (actor,),
                ).fetchone()[0]
                >= 500
                and kind != "review"
            ):
                raise ValueError("This workspace has reached its task limit")
            db.execute(
                "INSERT OR IGNORE INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    task_id,
                    actor,
                    session,
                    kind,
                    assignee,
                    manager,
                    "offered" if kind == "human" else "queued",
                    now,
                    0,
                    0,
                    parent,
                    now,
                    now,
                    json.dumps(body),
                ),
            )
        return self.get(actor, session, task_id)

    def get(self, actor, session, task_id):
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM tasks WHERE id=? AND actor=? AND session=?",
                (task_id, actor, session),
            ).fetchone()
        if not row:
            raise ValueError("Task not found")
        return self.unpack(row)

    def human_load(self, capacity_key):
        with self.connection() as db:
            return db.execute(
                "SELECT COUNT(*) FROM tasks WHERE kind='human' AND json_extract(body,'$.capacity_key')=? AND status IN ('offered','in_progress','submitted','changes_requested')",
                (capacity_key,),
            ).fetchone()[0]

    def recover_reviews(self):
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM tasks WHERE kind='human' AND status='submitted' LIMIT 500"
            ).fetchall()
        for row in rows:
            task = self.unpack(row)
            self.create(
                task["actor"],
                task["session"],
                title="Review: " + task["title"],
                description="Review the submitted human work against its brief.",
                kind="review",
                assignee=task["manager"],
                manager=task["manager"],
                parent=task["id"],
                dedupe=f"review:{task['id']}:{task['updated']}",
            )

    def list(self, actor, session):
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM tasks WHERE actor=? AND session=? ORDER BY created DESC LIMIT 200",
                (actor, session),
            ).fetchall()
        return [self.unpack(row) for row in rows]

    def update(
        self,
        actor,
        session,
        task_id,
        *,
        status,
        result=None,
        feedback=None,
        due=None,
        allowed=None,
        reset_attempts=False,
        verified_check=None,
    ):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM tasks WHERE id=? AND actor=? AND session=?",
                (task_id, actor, session),
            ).fetchone()
            if not row:
                raise ValueError("Task not found")
            if allowed and row["status"] not in allowed:
                raise ValueError(
                    "This task has already changed. Refresh and try again."
                )
            body = json.loads(row["body"])
            if result is not None:
                body["result"] = result
            if feedback is not None:
                body["feedback"] = feedback
            if verified_check is not None:
                body["verified_check"] = verified_check
            db.execute(
                "UPDATE tasks SET status=?, body=?, due=?, lease=0, updated=? WHERE id=?",
                (status, json.dumps(body), due or time.time(), time.time(), task_id),
            )
            if reset_attempts:
                db.execute("UPDATE tasks SET attempts=0 WHERE id=?", (task_id,))
        return self.get(actor, session, task_id)

    def claim(self, now=None):
        now = now or time.time()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "UPDATE tasks SET status=CASE WHEN attempts>=3 THEN 'blocked' ELSE 'queued' END, lease=0 WHERE status='running' AND lease<?",
                (now,),
            )
            row = db.execute(
                """SELECT t.* FROM tasks t JOIN companies c ON c.actor=t.actor AND c.session=t.session
                WHERE c.enabled=1 AND t.status='queued' AND t.due<=? AND t.attempts<3
                AND NOT EXISTS (SELECT 1 FROM tasks active WHERE active.actor=t.actor AND active.session=t.session AND active.status='running')
                ORDER BY t.created LIMIT 1""",
                (now,),
            ).fetchone()
            if not row:
                return None
            from developer_connections import connection

            own = connection(row["actor"])
            lease = 1200 if own and own.get("provider") == "vultr_model" else 300
            db.execute(
                "UPDATE tasks SET status='running', attempts=attempts+1, lease=?, updated=? WHERE id=?",
                (now + lease, now, row["id"]),
            )
        return self.get(row["actor"], row["session"], row["id"])

    def reserve_call(self, actor, session, maximum=36):
        day = time.strftime("%Y-%m-%d", time.gmtime())
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            enabled = db.execute(
                "SELECT enabled FROM companies WHERE actor=? AND session=?",
                (actor, session),
            ).fetchone()
            if not enabled or not enabled[0]:
                raise ValueError("Company work is paused")
            db.execute(
                "INSERT OR IGNORE INTO usage VALUES (?,?,?,0)", (actor, session, day)
            )
            used = db.execute(
                "SELECT requests FROM usage WHERE actor=? AND session=? AND day=?",
                (actor, session, day),
            ).fetchone()[0]
            if used >= maximum:
                raise ValueError("Company daily model request limit reached")
            db.execute(
                "UPDATE usage SET requests=requests+1 WHERE actor=? AND session=? AND day=?",
                (actor, session, day),
            )

    def reconcile_parents(self):
        with self.connection() as db:
            parents = db.execute(
                "SELECT * FROM tasks WHERE status='waiting_team'"
            ).fetchall()
        changed = []
        for row in parents:
            parent = self.unpack(row)
            with self.connection() as db:
                children = [
                    self.unpack(r)
                    for r in db.execute(
                        "SELECT * FROM tasks WHERE parent=?", (parent["id"],)
                    ).fetchall()
                ]
            if not children:
                continue
            blocked = any(t["status"] in {"blocked", "declined"} for t in children)
            finished = all(t["status"] in {"completed", "accepted"} for t in children)
            verified = any(t.get("verified_check") for t in children)
            if not blocked and not finished:
                continue
            status = (
                "blocked"
                if blocked or (parent.get("requires_check") and not verified)
                else "completed"
            )
            result = (
                "A team assignment needs attention. Review its result before continuing."
                if status == "blocked"
                else "\n\n".join(
                    t["title"] + ": " + (t["result"] or t["feedback"]) for t in children
                )[:16000]
            )
            try:
                changed.append(
                    self.update(
                        parent["actor"],
                        parent["session"],
                        parent["id"],
                        status=status,
                        result=result,
                        verified_check=verified,
                        allowed={"waiting_team"},
                    )
                )
            except ValueError:
                continue
        return changed

    def execution_metadata(
        self, actor, session, task_id, *, repository=None, delivery=None
    ):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT body FROM tasks WHERE id=? AND actor=? AND session=?",
                (task_id, actor, session),
            ).fetchone()
            if row is None:
                raise ValueError("Task not found")
            body = json.loads(row["body"])
            if delivery is not None:
                body["delivery"] = delivery
            else:
                body.update(
                    autonomous_request=True,
                    publish_repository=repository,
                    requires_check=True,
                )
            db.execute(
                "UPDATE tasks SET body=?, updated=? WHERE id=?",
                (json.dumps(body), time.time(), task_id),
            )
        return self.get(actor, session, task_id)

    def invitation(self, actor, session, employee):
        token = secrets.token_urlsafe(32)
        with self.connection() as db:
            db.execute(
                "DELETE FROM invites WHERE actor=? AND session=? AND employee=?",
                (actor, session, employee),
            )
            db.execute(
                "INSERT INTO invites VALUES (?,?,?,?,?)",
                (
                    hashlib.sha256(token.encode()).hexdigest(),
                    actor,
                    session,
                    employee,
                    time.time() + 7 * 86400,
                ),
            )
        return token

    def worker_access(self, token):
        if not token or len(token) > 200:
            raise PermissionError("A valid worker invitation is required")
        with self.connection() as db:
            row = db.execute(
                "SELECT actor,session,employee FROM invites WHERE digest=? AND expires>?",
                (hashlib.sha256(token.encode()).hexdigest(), time.time()),
            ).fetchone()
        if not row:
            raise PermissionError("This worker invitation is invalid or expired")
        return dict(row)

    def revoke(self, actor, session, employee):
        with self.connection() as db:
            db.execute(
                "DELETE FROM invites WHERE actor=? AND session=? AND employee=?",
                (actor, session, employee),
            )

    def delete_company(self, actor, session):
        with self.connection() as db:
            for table in ("companies", "tasks", "invites", "usage"):
                db.execute(
                    f"DELETE FROM {table} WHERE actor=? AND session=?", (actor, session)
                )

    def pause_actor(self, actor):
        with self.connection() as db:
            db.execute("UPDATE companies SET enabled=0 WHERE actor=?", (actor,))
