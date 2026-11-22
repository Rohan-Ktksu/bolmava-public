import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.exc import ArgumentError

from tests.db_guard import check_test_database

APP = "postgresql+psycopg://bolmava:bolmava@localhost:5432/bolmava"
TEST = "postgresql+psycopg://bolmava_test:bolmava_test@localhost:5432/bolmava_test"


@pytest.mark.parametrize("url, app, reason", [
    ("postgresql+psycopg://u:p@localhost:5432/bolmava", APP, "_test"),
    ("postgresql+psycopg://u:p@db.example.com:5432/bolmava_test", APP, "not local"),
    ("postgresql+psycopg://u:p@127.0.0.1:5432/bolmava_test", APP + "_test", "application database"),
    # R1a: query parameters that would reroute the driver
    (TEST + "?dbname=bolmava", APP, "connection parameters"),
    (TEST + "?host=db.example.com", APP, "connection parameters"),
    (TEST + "?hostaddr=10.0.0.5", APP, "connection parameters"),
    (TEST + "?port=6543", APP, "connection parameters"),
    (TEST + "?service=prod", APP, "connection parameters"),
    # targets that leave routing to libpq environment defaults
    ("postgresql+psycopg://u:p@/bolmava_test", APP, "explicitly"),
    ("postgresql+psycopg://u:p@localhost/bolmava_test", APP, "explicitly"),
    # the application URL's effective target counts, not its path
    (TEST, "postgresql+psycopg://bolmava:bolmava@localhost:5432/bolmava?dbname=bolmava_test", "application database"),
    # R1b: the same port written as a query string, with and without a localhost alias
    (TEST, TEST + "?port=5432", "application database"),
    (TEST, TEST.replace("localhost", "127.0.0.1") + "?port=5432", "application database"),
    (TEST, "postgresql+psycopg://u:p@/bolmava_test?host=LOCALHOST&port=5432", "application database"),
    (TEST, "postgresql+psycopg://u:p@localhost/bolmava_test", "application database"),  # app relies on default port
])
def test_rejected_targets(url, app, reason):
    with pytest.raises(ValueError, match=reason):
        check_test_database(url, app, env={})


def test_unreadable_port_refuses():
    # conftest refuses on any exception from the guard, not only ValueError
    with pytest.raises(ArgumentError):
        check_test_database(TEST, TEST + "?port=54x2", env={})


@pytest.mark.parametrize("name", ["PGHOSTADDR", "PGSERVICE"])
def test_routing_environment_rejected(name):
    with pytest.raises(ValueError, match=name):
        check_test_database(TEST, APP, env={name: "x"})


def test_accepted_targets():
    check_test_database(TEST, APP, env={})
    check_test_database(TEST, TEST + "?port=5433", env={})  # same name on a genuinely different port
    check_test_database(TEST + "?sslmode=disable&connect_timeout=5", APP, env={})
    check_test_database("postgresql+psycopg://u:p@postgres:5432/bolmava_test", APP, allowed_host="postgres", env={})


@pytest.mark.parametrize("env", [
    {"BOLMAVA_DESTRUCTIVE_TESTS": "1", "TEST_DATABASE_URL": "postgresql+psycopg://u:p@localhost:1/bolmava"},
    {"BOLMAVA_DESTRUCTIVE_TESTS": "", "TEST_DATABASE_URL": "postgresql+psycopg://u:p@localhost:1/bolmava_test"},
    {"BOLMAVA_DESTRUCTIVE_TESTS": "1", "TEST_DATABASE_URL": "postgresql+psycopg://u:p@localhost:1/bolmava_test?dbname=bolmava"},
    {"BOLMAVA_DESTRUCTIVE_TESTS": "1", "TEST_DATABASE_URL": "postgresql+psycopg://u:p@localhost:1/bolmava_test?host=db.example.com"},
])
def test_refuses_before_any_database_call(env):
    # Port 1 has no server: any migration, truncate, or connection attempt would surface as a connection error.
    backend = Path(__file__).parent.parent
    probe = "import sys, pytest; sys.exit(pytest.main(['-q', '-p', 'no:cacheprovider', 'tests/test_identity.py::test_health']))"
    r = subprocess.run([sys.executable, "-c", probe], cwd=backend, env=os.environ | env, capture_output=True, text=True)
    out = r.stdout + r.stderr
    assert r.returncode != 0
    assert "Refusing to run" in out
    assert "OperationalError" not in out and "alembic" not in out.lower()
