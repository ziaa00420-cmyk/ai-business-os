from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AuditLog


def record(
    session: Session,
    business_id: UUID,
    action: str,
    *,
    actor_type: str = "user",
    actor_id: UUID | str | None = None,
    target_type: str | None = None,
    target_id: UUID | str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            business_id=business_id,
            actor_type=actor_type,
            actor_id=str(actor_id) if actor_id else None,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id else None,
            detail=detail or {},
        )
    )
