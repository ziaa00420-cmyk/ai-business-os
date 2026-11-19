"""Task table and runner: the skeleton of the Central AI Manager.

Stage 1 has two task kinds (profile drafting, PDF catalogue extraction). Each
task is a row with input, output, status and attempts, and every model call it
makes is linked to it. A failed task is retried once and then handed to the
owner ("needs_owner"), as the plan describes.

Tasks run in-process via FastAPI background tasks for now. The handler
signature is what a Procrastinate worker will call in stage 2, so moving them
out of the web process does not change handler code.
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db import scoped_session
from app.models import Task
from app.services import audit

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 2

# handler(session, task) -> output dict
Handler = Callable[[Session, Task], dict[str, Any]]
HANDLERS: dict[str, Handler] = {}


def handler(kind: str):
    def register(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn

    return register


def create_task(
    session: Session,
    business_id: UUID,
    kind: str,
    agent: str,
    input: dict[str, Any],
    created_by: UUID | None,
) -> Task:
    task = Task(business_id=business_id, kind=kind, agent=agent, input=input, created_by=created_by)
    session.add(task)
    session.flush()
    audit.record(
        session,
        business_id,
        "task.created",
        actor_id=created_by,
        target_type="task",
        target_id=task.id,
        detail={"kind": kind},
    )
    return task


def run_task(task_id: UUID, business_id: UUID, user_id: UUID) -> None:
    """Run a task to completion, retrying once. Safe to call from a background thread."""
    while True:
        with scoped_session(user_id, business_id) as session:
            task = session.get(Task, task_id)
            if task is None or task.status in ("succeeded", "needs_owner"):
                return
            task.status = "running"
            task.attempts += 1
            task.started_at = datetime.now(UTC)
            attempt = task.attempts
        try:
            with scoped_session(user_id, business_id) as session:
                task = session.get(Task, task_id)
                assert task is not None
                output = HANDLERS[task.kind](session, task)
                task.output = output
                task.status = "succeeded"
                task.error = None
                task.finished_at = datetime.now(UTC)
                audit.record(
                    session,
                    business_id,
                    "task.succeeded",
                    actor_type="agent",
                    actor_id=task.agent,
                    target_type="task",
                    target_id=task.id,
                )
            return
        except Exception as exc:  # noqa: BLE001 - every failure is recorded on the task
            log.exception("task %s attempt %s failed", task_id, attempt)
            with scoped_session(user_id, business_id) as session:
                task = session.get(Task, task_id)
                assert task is not None
                task.error = f"{type(exc).__name__}: {exc}"[:2000]
                final = attempt >= MAX_ATTEMPTS
                task.status = "needs_owner" if final else "queued"
                if final:
                    task.finished_at = datetime.now(UTC)
                    audit.record(
                        session,
                        business_id,
                        "task.failed",
                        actor_type="agent",
                        actor_id=task.agent,
                        target_type="task",
                        target_id=task.id,
                        detail={"error": task.error},
                    )
                    on_fail = FAILURE_HOOKS.get(task.kind)
                    if on_fail:
                        on_fail(session, task)
            if final:
                return


# Called inside the final failure transaction so dependent rows can be marked too.
FAILURE_HOOKS: dict[str, Callable[[Session, Task], None]] = {}
