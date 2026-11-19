import json

from fastapi import APIRouter, Depends
from sqlalchemy import select, text

from app.auth import BusinessContext, CurrentUser, business_context, current_user, require_owner
from app.db import scoped_session
from app.models import AuditLog, Business, Membership
from app.schemas import (
    AuditOut,
    BusinessCreate,
    BusinessOut,
    BusinessSummary,
    MeOut,
    OnboardingUpdate,
)
from app.services import audit

router = APIRouter(tags=["businesses"])


@router.get("/me", response_model=MeOut)
def me(user: CurrentUser = Depends(current_user)):
    with scoped_session(user.id) as session:
        rows = session.execute(
            select(Business, Membership.role)
            .join(Membership, Membership.business_id == Business.id)
            .where(Membership.user_id == user.id)
            .order_by(Business.created_at)
        ).all()
        return MeOut(
            id=user.id,
            email=user.email,
            businesses=[
                BusinessSummary(id=b.id, name=b.name, onboarding_step=b.onboarding_step, role=r)
                for b, r in rows
            ],
        )


@router.post("/businesses", response_model=BusinessOut, status_code=201)
def create_business(body: BusinessCreate, user: CurrentUser = Depends(current_user)):
    with scoped_session(user.id) as session:
        business_id = session.scalar(
            text("select create_business(:name, cast(:answers as jsonb))"),
            {"name": body.name, "answers": json.dumps({"company_name": body.name})},
        )
    with scoped_session(user.id, business_id) as session:
        return BusinessOut.model_validate(session.get(Business, business_id))


@router.get("/businesses/{business_id}", response_model=BusinessOut)
def get_business(ctx: BusinessContext = Depends(business_context)):
    with scoped_session(ctx.user.id, ctx.business_id) as session:
        return BusinessOut.model_validate(session.get(Business, ctx.business_id))


@router.put("/businesses/{business_id}/onboarding", response_model=BusinessOut)
def save_onboarding(body: OnboardingUpdate, ctx: BusinessContext = Depends(require_owner)):
    with scoped_session(ctx.user.id, ctx.business_id) as session:
        business = session.get(Business, ctx.business_id)
        assert business is not None
        answers = body.answers.model_dump(mode="json", exclude_none=True)
        business.onboarding = answers
        if answers.get("company_name"):
            business.name = answers["company_name"]
        if body.step:
            business.onboarding_step = body.step
        audit.record(
            session,
            ctx.business_id,
            "onboarding.saved",
            actor_id=ctx.user.id,
            target_type="business",
            target_id=ctx.business_id,
            detail={"step": body.step, "fields": sorted(answers)},
        )
        session.flush()
        session.refresh(business)
        return BusinessOut.model_validate(business)


@router.get("/businesses/{business_id}/audit", response_model=list[AuditOut])
def recent_audit(ctx: BusinessContext = Depends(business_context)):
    with scoped_session(ctx.user.id, ctx.business_id) as session:
        rows = session.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(100)).all()
        return [AuditOut.model_validate(r) for r in rows]
