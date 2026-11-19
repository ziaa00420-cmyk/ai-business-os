import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://aibos_app:aibos_app@localhost:5432/aibos_test"
)
os.environ.setdefault(
    "MIGRATIONS_DATABASE_URL", "postgresql+psycopg://aibos:aibos@localhost:5432/aibos_test"
)
os.environ["AUTH_MODE"] = "dev"
os.environ["ANTHROPIC_API_KEY"] = ""

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

OWNER_URL = os.environ["MIGRATIONS_DATABASE_URL"]


@pytest.fixture(scope="session", autouse=True)
def database(tmp_path_factory):
    os.environ["STORAGE_DIR"] = str(tmp_path_factory.mktemp("storage"))
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option(
        "script_location", os.path.join(os.path.dirname(__file__), "..", "migrations")
    )
    cfg.set_main_option("sqlalchemy.url", OWNER_URL)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def clean_tables():
    yield
    engine = create_engine(OWNER_URL)
    with engine.begin() as conn:
        conn.execute(text("truncate users, businesses cascade"))
    engine.dispose()


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


def headers(email: str) -> dict[str, str]:
    return {"X-User-Email": email}


@pytest.fixture
def owner(client):
    h = headers("owner@example.com")
    r = client.post("/api/businesses", json={"name": "Sialkot Steelworks"}, headers=h)
    assert r.status_code == 201, r.text
    return {"h": h, "id": r.json()["id"]}
