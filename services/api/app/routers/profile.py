from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.auth import BusinessContext, business_context, require_owner
from app.db import scoped_session
from app.models import Business, ProfileVersion, Task
from app.profile_schema import BusinessProfile
from app.schemas import ProfileState, ProfileVersionOut, TaskOut
from app.services import audit
from app.services.model_gateway import model_available
from app.services.tasks import create_task, run_task

router = APIRouter(tags=["profile"])


def _state(session) -> ProfileState:
    draft = session.scalars(
        select(ProfileVersion)
        .where(ProfileVersion.status == "draft")
        .order_by(ProfileVersion.version.desc())
        .limit(1)
    ).first()
    approved = session.scalars(
        select(ProfileVersion).where(ProfileVersion.status == "approved")
    ).first()
    pending = session.scalars(
        select(Task)
        .where(Task.kind == "profile.draft", Task.status.in_(["queued", "running"]))
        .order_by(Task.created_at.desc())
        .limit(1)
    ).first()
    # A draft older than the approved version is stale.
    if draft and approved and draft.version < approved.version:
        draft = None
    return ProfileState(
        draft=ProfileVersionOut.model_validate(draft) if draft else None,
        approved=ProfileVersionOut.model_validate(approved) if approved else None,
        pending_task=TaskOut.model_validate(pending) if pending else None,
        model_enabled=model_available(),
    )


@router.get("/businesses/{business_id}/profile", response_model=ProfileState)
def get_profile(ctx: BusinessContext = Depends(business_context)):
    with scoped_session(ctx.user.id, ctx.business_id) as session:
        return _state(session)


@router.post("/businesses/{business_id}/profile/draft", response_model=TaskOut, status_code=202)
def request_draft(background: BackgroundTasks, ctx: BusinessContext = Depends(require_owner)):
    with scoped_session(ctx.user.id, ctx.business_id) as session:
        running = session.scalars(
            select(Task).where(Task.kind == "profile.draft", Task.status.in_(["queued", "running"]))
        ).first()
        if running:
            return TaskOut.model_validate(running)
        task = create_task(session, ctx.business_id, "profile.draft", "profile", {}, ctx.user.id)
        out = TaskOut.model_validate(task)
    background.add_task(run_task, task.id, ctx.business_id, ctx.user.id)
    return out


@router.put("/businesses/{business_id}/profile/{version_id}", response_model=ProfileVersionOut)
def edit_draft(version_id: UUID, profile: dict, ctx: BusinessContext = Depends(require_owner)):
    try:
        validated = BusinessProfile.model_validate(profile)
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_url=False)) from exc
    with scoped_session(ctx.user.id, ctx.business_id) as session:
        version = session.get(ProfileVersion, version_id)
        if version is None:
            raise HTTPException(404, "Profile version not found")
        if version.status != "draft":
            raise HTTPException(409, "Only a draft can be edited; ask for a new draft instead")
        version.profile = validated.model_dump(mode="json")
        audit.record(
            session,
            ctx.business_id,
            "profile.edited",
            actor_id=ctx.user.id,
            target_type="profile_version",
            target_id=version.id,
        )
        return ProfileVersionOut.model_validate(version)


@router.post(
    "/businesses/{business_id}/profile/{version_id}/approve", response_model=ProfileVersionOut
)
def approve(version_id: UUID, ctx: BusinessContext = Depends(require_owner)):
    with scoped_session(ctx.user.id, ctx.business_id) as session:
        version = session.get(ProfileVersion, version_id, with_for_update=True)
        if version is None:
            raise HTTPException(404, "Profile version not found")
        if version.status != "draft":
            raise HTTPException(409, f"This version is already {version.status}")
        BusinessProfile.model_validate(version.profile)
        for previous in session.scalars(
            select(ProfileVersion).where(ProfileVersion.status == "approved")
        ).all():
            previous.status = "superseded"
        session.flush()
        version.status = "approved"
        version.approved_by = ctx.user.id
        version.approved_at = datetime.now(UTC)
        business = session.get(Business, ctx.business_id)
        if business:
            business.onboarding_step = "done"
        audit.record(
            session,
            ctx.business_id,
            "profile.approved",
            actor_id=ctx.user.id,
            target_type="profile_version",
            target_id=version.id,
            detail={"version": version.version},
        )
        session.flush()
        return ProfileVersionOut.model_validate(version)


@router.get("/businesses/{business_id}/tasks", response_model=list[TaskOut])
def list_tasks(ctx: BusinessContext = Depends(business_context)):
    with scoped_session(ctx.user.id, ctx.business_id) as session:
        tasks = session.scalars(select(Task).order_by(Task.created_at.desc()).limit(50)).all()
        return [TaskOut.model_validate(t) for t in tasks]


@router.get("/businesses/{business_id}/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: UUID, ctx: BusinessContext = Depends(business_context)):
    with scoped_session(ctx.user.id, ctx.business_id) as session:
        task = session.get(Task, task_id)
        if task is None:
            raise HTTPException(404, "Task not found")
        return TaskOut.model_validate(task)
