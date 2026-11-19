"""Database engine and tenant-scoped sessions.

Every request that touches business data runs inside a transaction where
`app.user_id` and `app.business_id` are set with SET LOCAL. Postgres row-level
security policies (see migrations) read those settings, so a query can never
see another business's rows even if application code forgets a filter.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def _session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def set_context(session: Session, user_id: UUID | None, business_id: UUID | None) -> None:
    # set_config(..., true) is the function form of SET LOCAL and accepts bind params.
    session.execute(
        text("select set_config('app.user_id', :u, true), set_config('app.business_id', :b, true)"),
        {"u": str(user_id) if user_id else "", "b": str(business_id) if business_id else ""},
    )


@contextmanager
def scoped_session(
    user_id: UUID | None = None, business_id: UUID | None = None
) -> Iterator[Session]:
    session = _session_factory()()
    try:
        with session.begin():
            set_context(session, user_id, business_id)
            yield session
    finally:
        session.close()
