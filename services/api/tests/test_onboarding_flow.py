from pathlib import Path

from app.profile_schema import BusinessProfile, ProfileDraft

FIXTURE = Path(__file__).parent / "fixtures" / "price_list.csv"


def upload(client, owner, path: Path, kind="price_list", name=None):
    with path.open("rb") as f:
        r = client.post(
            f"/api/businesses/{owner['id']}/documents",
            files={"file": (name or path.name, f)},
            data={"kind": kind},
            headers=owner["h"],
        )
    assert r.status_code == 201, r.text
    return r.json()


def test_full_onboarding_flow(client, owner):
    bid, h = owner["id"], owner["h"]

    me = client.get("/api/me", headers=h).json()
    assert [b["id"] for b in me["businesses"]] == [bid]

    answers = {
        "company_name": "Sialkot Steelworks Ltd",
        "country": "Pakistan",
        "city": "Sialkot",
        "business_type": "manufacturer",
        "description": "Family-run foundry making cast-iron cookware since 1998.",
        "certifications": ["ISO 9001"],
        "target_markets": ["United Kingdom", "Germany"],
        "default_currency": "usd",
        "contact_email": "export@example.com",
    }
    r = client.put(
        f"/api/businesses/{bid}/onboarding",
        json={"answers": answers, "step": "documents"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Sialkot Steelworks Ltd"
    assert r.json()["onboarding"]["default_currency"] == "USD"

    doc = upload(client, owner, FIXTURE)
    r = client.post(
        f"/api/businesses/{bid}/catalogue-imports", json={"document_id": doc["id"]}, headers=h
    )
    assert r.status_code == 201, r.text
    imp = r.json()
    assert imp["status"] == "mapping"
    assert imp["total_rows"] == 5 and imp["importable_rows"] == 4

    # Owner corrects the mapping: send the Finish column to description.
    mapping = imp["mapping"] | {"description": "Finish"}
    r = client.put(
        f"/api/businesses/{bid}/catalogue-imports/{imp['id']}/mapping",
        json={"mapping": mapping},
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["preview"][0]["description"] == "Pre-seasoned"

    r = client.post(
        f"/api/businesses/{bid}/catalogue-imports/{imp['id']}/commit", json={}, headers=h
    )
    assert r.status_code == 200, r.text
    assert r.json()["created_count"] == 4 and r.json()["status"] == "committed"

    # Committing twice is refused.
    r = client.post(
        f"/api/businesses/{bid}/catalogue-imports/{imp['id']}/commit", json={}, headers=h
    )
    assert r.status_code == 409

    products = client.get(f"/api/businesses/{bid}/products", headers=h).json()
    assert products["total"] == 4
    skillet = next(p for p in products["items"] if p["sku"] == "CI-1001")
    assert skillet["unit_price"] == "12.5000" and skillet["currency"] == "USD"

    # Re-importing the same list updates by SKU instead of duplicating.
    doc2 = upload(client, owner, FIXTURE)
    imp2 = client.post(
        f"/api/businesses/{bid}/catalogue-imports", json={"document_id": doc2["id"]}, headers=h
    ).json()
    r = client.post(
        f"/api/businesses/{bid}/catalogue-imports/{imp2['id']}/commit", json={}, headers=h
    ).json()
    assert r["created_count"] == 1 and r["updated_count"] == 3  # Grill Press has no SKU
    assert client.get(f"/api/businesses/{bid}/products", headers=h).json()["total"] == 5

    # Profile draft without a model key falls back to the owner's answers.
    r = client.post(f"/api/businesses/{bid}/profile/draft", headers=h)
    assert r.status_code == 202, r.text
    task = client.get(f"/api/businesses/{bid}/tasks/{r.json()['id']}", headers=h).json()
    assert task["status"] == "succeeded", task

    state = client.get(f"/api/businesses/{bid}/profile", headers=h).json()
    draft = state["draft"]
    assert draft["source"] == "fallback" and state["approved"] is None
    assert draft["profile"]["company_name"] == "Sialkot Steelworks Ltd"
    assert draft["profile"]["product_categories"] == ["Cookware", "Accessories"]
    assert any(n["field"] == "production_capacity" for n in draft["notes"])

    edited = draft["profile"] | {"production_capacity": "20,000 pieces per month"}
    r = client.put(f"/api/businesses/{bid}/profile/{draft['id']}", json=edited, headers=h)
    assert r.status_code == 200, r.text

    r = client.post(f"/api/businesses/{bid}/profile/{draft['id']}/approve", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert (
        client.post(f"/api/businesses/{bid}/profile/{draft['id']}/approve", headers=h).status_code
        == 409
    )
    assert (
        client.put(
            f"/api/businesses/{bid}/profile/{draft['id']}", json=edited, headers=h
        ).status_code
        == 409
    )

    state = client.get(f"/api/businesses/{bid}/profile", headers=h).json()
    assert state["approved"]["profile"]["production_capacity"] == "20,000 pieces per month"
    assert client.get(f"/api/businesses/{bid}", headers=h).json()["onboarding_step"] == "done"

    # A second approved version supersedes the first.
    client.post(f"/api/businesses/{bid}/profile/draft", headers=h)
    state = client.get(f"/api/businesses/{bid}/profile", headers=h).json()
    assert state["draft"]["version"] == 2
    client.post(f"/api/businesses/{bid}/profile/{state['draft']['id']}/approve", headers=h)
    state = client.get(f"/api/businesses/{bid}/profile", headers=h).json()
    assert state["approved"]["version"] == 2 and state["draft"] is None

    actions = [a["action"] for a in client.get(f"/api/businesses/{bid}/audit", headers=h).json()]
    for expected in (
        "business.created",
        "document.uploaded",
        "catalogue.import_committed",
        "profile.drafted",
        "profile.approved",
    ):
        assert expected in actions


def test_profile_draft_uses_model_when_configured(client, owner, monkeypatch):
    from app.services import profile_drafter

    captured = {}

    def fake_call(session, **kwargs):
        captured.update(kwargs)
        return ProfileDraft(profile=BusinessProfile(company_name="From AI", country="Pakistan"))

    monkeypatch.setattr(profile_drafter, "model_available", lambda: True)
    monkeypatch.setattr(profile_drafter, "structured_call", fake_call)
    client.put(
        f"/api/businesses/{owner['id']}/onboarding",
        json={"answers": {"country": "Pakistan"}},
        headers=owner["h"],
    )
    client.post(f"/api/businesses/{owner['id']}/profile/draft", headers=owner["h"])
    draft = client.get(f"/api/businesses/{owner['id']}/profile", headers=owner["h"]).json()["draft"]
    assert draft["source"] == "ai" and draft["profile"]["company_name"] == "From AI"
    assert "<owner_answers>" in captured["user_content"]
    assert "untrusted" in captured["system"]


def test_pdf_import_needs_model(client, owner, tmp_path):
    from pypdf import PdfWriter

    w = PdfWriter()
    w.add_blank_page(200, 200)
    path = tmp_path / "catalogue.pdf"
    with path.open("wb") as f:
        w.write(f)
    doc = upload(client, owner, path, kind="catalogue")
    assert doc["page_count"] == 1 and doc["has_text"] is False
    r = client.post(
        f"/api/businesses/{owner['id']}/catalogue-imports",
        json={"document_id": doc["id"]},
        headers=owner["h"],
    )
    assert r.status_code == 409


def test_pdf_import_with_model(client, owner, tmp_path, monkeypatch):
    from pypdf import PdfWriter

    from app.routers import catalogue as catalogue_router
    from app.routers import documents as documents_router
    from app.services import catalogue_tasks
    from app.services.catalogue import ExtractedProduct, ExtractedProducts

    monkeypatch.setattr(
        documents_router,
        "extract_pdf_text",
        lambda data: ("--- page 2 ---\nCI-1001 Skillet 10in USD 12.50", 3),
    )
    monkeypatch.setattr(catalogue_router, "model_available", lambda: True)
    calls = {"n": 0}

    def fake_call(session, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")  # first attempt fails, retry succeeds
        return ExtractedProducts(
            products=[
                ExtractedProduct(sku="CI-1001", name="Skillet 10in", unit_price="USD 12.50", page=2)
            ]
        )

    monkeypatch.setattr(catalogue_tasks, "structured_call", fake_call)
    w = PdfWriter()
    w.add_blank_page(200, 200)
    path = tmp_path / "catalogue.pdf"
    with path.open("wb") as f:
        w.write(f)
    doc = upload(client, owner, path, kind="catalogue")
    r = client.post(
        f"/api/businesses/{owner['id']}/catalogue-imports",
        json={"document_id": doc["id"]},
        headers=owner["h"],
    )
    assert r.status_code == 201 and r.json()["status"] == "extracting"
    imp = client.get(
        f"/api/businesses/{owner['id']}/catalogue-imports/{r.json()['id']}", headers=owner["h"]
    ).json()
    assert imp["status"] == "mapping", imp
    assert imp["task"]["attempts"] == 2 and imp["task"]["status"] == "succeeded"
    assert imp["preview"][0]["unit_price"] == "12.50"
    assert imp["preview"][0]["attributes"] == {"page": 2}


def test_pdf_import_failure_goes_to_owner(client, owner, tmp_path, monkeypatch):
    from pypdf import PdfWriter

    from app.routers import catalogue as catalogue_router
    from app.routers import documents as documents_router
    from app.services import catalogue_tasks

    monkeypatch.setattr(documents_router, "extract_pdf_text", lambda data: ("some text", 1))
    monkeypatch.setattr(catalogue_router, "model_available", lambda: True)

    def always_fail(session, **kwargs):
        raise RuntimeError("model down")

    monkeypatch.setattr(catalogue_tasks, "structured_call", always_fail)
    w = PdfWriter()
    w.add_blank_page(200, 200)
    path = tmp_path / "c.pdf"
    with path.open("wb") as f:
        w.write(f)
    doc = upload(client, owner, path, kind="catalogue")
    r = client.post(
        f"/api/businesses/{owner['id']}/catalogue-imports",
        json={"document_id": doc["id"]},
        headers=owner["h"],
    )
    imp = client.get(
        f"/api/businesses/{owner['id']}/catalogue-imports/{r.json()['id']}", headers=owner["h"]
    ).json()
    assert imp["status"] == "failed"
    assert imp["task"]["status"] == "needs_owner" and "model down" in imp["task"]["error"]


def test_upload_rejects_unknown_types(client, owner):
    r = client.post(
        f"/api/businesses/{owner['id']}/documents",
        files={"file": ("run.exe", b"MZ")},
        headers=owner["h"],
    )
    assert r.status_code == 415


def test_requires_sign_in(client):
    assert client.get("/api/me").status_code == 401
