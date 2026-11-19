"""Who is calling, and for which business.

AUTH_MODE=dev trusts an X-User-Email header so the stack runs locally without
an identity provider. It refuses to start that way unless explicitly chosen.
AUTH_MODE=clerk verifies the Clerk session JWT (Authorization: Bearer ...)
against Clerk's JWKS and uses the token's `sub` and `email` claims.
"""

from dataclasses import dataclass
from functools import lru_cache
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select

from app.config import get_settings
from app.db import scoped_session
from app.models import Membership, User


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    email: str


@dataclass(frozen=True)
class BusinessContext:
    user: CurrentUser
    business_id: UUID
    role: str


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True)


def _identity_from_request(authorization: str | None, x_user_email: str | None) -> tuple[str, str]:
    settings = get_settings()
    if settings.auth_mode == "dev":
        if not x_user_email or "@" not in x_user_email:
            raise HTTPException(401, "Sign in first (dev mode needs an X-User-Email header)")
        email = x_user_email.strip().lower()
        return f"dev:{email}", email
    if settings.auth_mode == "clerk":
        if not settings.clerk_jwks_url:
            raise HTTPException(500, "CLERK_JWKS_URL is not configured")
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(401, "Missing bearer token")
        token = authorization.split(" ", 1)[1]
        try:
            key = _jwks_client(settings.clerk_jwks_url).get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                issuer=settings.clerk_issuer,
                options={"verify_aud": False, "require": ["exp", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise HTTPException(401, "Invalid session token") from exc
        email = claims.get("email")
        if not email:
            raise HTTPException(401, "Session token has no email claim; add it in Clerk")
        return f"clerk:{claims['sub']}", str(email).lower()
    raise HTTPException(500, f"Unknown AUTH_MODE {settings.auth_mode}")


def current_user(
    authorization: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
) -> CurrentUser:
    external_id, email = _identity_from_request(authorization, x_user_email)
    with scoped_session() as session:
        user = session.scalar(select(User).where(User.external_id == external_id))
        if user is None:
            user = session.scalar(select(User).where(User.email == email))
            if user is None:
                user = User(email=email, external_id=external_id)
                session.add(user)
            else:
                user.external_id = external_id
            session.flush()
        return CurrentUser(id=user.id, email=user.email)


def business_context(
    business_id: UUID, user: CurrentUser = Depends(current_user)
) -> BusinessContext:
    with scoped_session(user.id) as session:
        membership = session.get(Membership, (business_id, user.id))
        if membership is None:
            # Same answer whether the business exists or not.
            raise HTTPException(404, "Business not found")
        return BusinessContext(user=user, business_id=business_id, role=membership.role)


def require_owner(ctx: BusinessContext = Depends(business_context)) -> BusinessContext:
    if ctx.role != "owner":
        raise HTTPException(403, "Only the owner can do this")
    return ctx
