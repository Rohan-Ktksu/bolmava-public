import os

import pytest

from app import config
from tests.db_guard import check_test_database

# The fixtures below downgrade and truncate the database, so check the target before anything connects.
TEST_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://bolmava_test:bolmava_test@localhost:5432/bolmava_test")
if os.environ.get("BOLMAVA_DESTRUCTIVE_TESTS") != "1":
    raise pytest.UsageError("Refusing to run: tests erase TEST_DATABASE_URL. Set BOLMAVA_DESTRUCTIVE_TESTS=1 to confirm it is disposable.")
try:
    check_test_database(TEST_URL, config.settings.database_url, os.environ.get("TEST_DATABASE_ALLOWED_HOST"))
except Exception as e:  # any unparseable target is refused too
    raise pytest.UsageError(f"Refusing to run against TEST_DATABASE_URL: {e}")

os.environ["DATABASE_URL"] = TEST_URL
os.environ["APP_ENV"] = "test"
os.environ["AUTH_MODE"] = "local"
config.settings = config.Settings()  # rebuild before app.db reads it, so the app engine uses the test database

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402

TABLES = (
    "handoffs, case_evidence, case_updates, cases, fulfillment_events, payment_reversals, payment_events, payment_requests, staff_grants, "
    "pending_actions, messages, conversations, stock_movements, orders, quotes, rfqs, "
    "audit_events, products, memberships, organizations, users"
)


@pytest.fixture(scope="session", autouse=True)
def migrated():
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def fresh_data(migrated):
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    with SessionLocal() as db:
        seed(db)


@pytest.fixture
def client():
    return TestClient(app)


def login(client: TestClient, email: str) -> dict:
    r = client.post("/api/v1/auth/local/session", json={"email": email})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
