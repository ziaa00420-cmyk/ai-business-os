"""Row-level security: one business can never see another's data."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.db import scoped_session
from app.models import AuditLog, Product, User
from tests.conftest import headers
from tests.test_onboarding_flow import FIXTURE, upload


def _import(client, owner):
    doc = upload(client, owner, FIXTURE)
    imp = client.post(
        f"/api/businesses/{owner['id']}/catalogue-imports",
        json={"document_id": doc["id"]},
        headers=owner["h"],
    ).json()
    client.post(
        f"/api/businesses/{owner['id']}/catalogue-imports/{imp['id']}/commit",
        json={},
        headers=owner["h"],
    )
    return doc, imp


def test_other_user_cannot_reach_business(client, owner):
    doc, imp = _import(client, owner)
    other = headers("intruder@example.com")
    client.post("/api/businesses", json={"name": "Other Co"}, headers=other)
    bid = owner["id"]
    for path in (
        "",
        "/products",
        "/documents",
        "/profile",
        "/audit",
        f"/catalogue-imports/{imp['id']}",
    ):
        assert client.get(f"/api/businesses/{bid}{path}", headers=other).status_code == 404, path
    assert (
        client.put(
            f"/api/businesses/{bid}/onboarding", json={"answers": {}}, headers=other
        ).status_code
        == 404
    )
    assert [b["name"] for b in client.get("/api/me", headers=other).json()["businesses"]] == [
        "Other Co"
    ]


def test_database_blocks_cross_tenant_reads_even_without_app_filters(client, owner):
    _import(client, owner)
    other = headers("intruder@example.com")
    other_bid = client.post("/api/businesses", json={"name": "Other Co"}, headers=other).json()[
        "id"
    ]
    with scoped_session() as session:
        intruder = session.scalar(select(User).where(User.email == "intruder@example.com"))
        owner_user = session.scalar(select(User).where(User.email == "owner@example.com"))

    # Owner context sees their products.
    with scoped_session(owner_user.id, owner["id"]) as session:
        assert len(session.scalars(select(Product)).all()) == 4
    # Intruder claiming the owner's business id sees nothing (not a member).
    with scoped_session(intruder.id, owner["id"]) as session:
        assert session.scalars(select(Product)).all() == []
        assert session.execute(text("select count(*) from businesses")).scalar() == 1
    # Intruder in their own business sees nothing of the owner's.
    with scoped_session(intruder.id, other_bid) as session:
        assert session.scalars(select(Product)).all() == []
    # No context at all sees nothing.
    with scoped_session() as session:
        assert session.scalars(select(Product)).all() == []


def test_cannot_write_into_another_business(client, owner):
    other = headers("intruder@example.com")
    other_bid = client.post("/api/businesses", json={"name": "Other Co"}, headers=other).json()[
        "id"
    ]
    with scoped_session() as session:
        intruder = session.scalar(select(User).where(User.email == "intruder@example.com"))
    with pytest.raises(DBAPIError):
        with scoped_session(intruder.id, other_bid) as session:
            session.add(Product(business_id=owner["id"], name="planted"))
            session.flush()


def test_audit_log_is_append_only(client, owner):
    with scoped_session() as session:
        owner_user = session.scalar(select(User).where(User.email == "owner@example.com"))
    with pytest.raises(DBAPIError):
        with scoped_session(owner_user.id, owner["id"]) as session:
            session.execute(text("update audit_log set action = 'x'"))
    with pytest.raises(DBAPIError):
        with scoped_session(owner_user.id, owner["id"]) as session:
            session.execute(text("delete from audit_log"))
    with scoped_session(owner_user.id, owner["id"]) as session:
        assert session.scalars(select(AuditLog)).first() is not None
