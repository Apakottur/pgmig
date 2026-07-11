from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
import shpyx
import tenacity
from psycopg import sql
from psycopg.conninfo import make_conninfo

from tests.harness import Db, GenerateSetup

_COMPOSE_FILE = Path(__file__).parent / "docker-compose.yml"
_ADMIN_DSN = "postgresql://pgmig:pgmig@localhost:55432/pgmig"
_SRC_DB = "pgmig_src"
_DST_DB = "pgmig_dst"


@tenacity.retry(
    retry=tenacity.retry_if_exception_type(psycopg.OperationalError),
    wait=tenacity.wait_fixed(0.5),
    stop=tenacity.stop_after_delay(60),
    reraise=True,
)
def _wait_until_ready(dsn: str) -> None:
    # Poll until the server accepts connections and answers a query. We do not
    # rely on `docker compose --wait` or a container healthcheck for readiness.
    with psycopg.connect(dsn) as conn:
        conn.execute("SELECT 1")


def _recreate_database(admin_dsn: str, name: str) -> None:
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))


def _clear(dsn: str) -> None:
    # Drop every non-system schema (and whatever it contains) and recreate an
    # empty `public`, so each test starts from a blank schema.
    with psycopg.connect(dsn, autocommit=True) as conn:
        schemas = conn.execute(
            "SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname <> 'information_schema'"
        ).fetchall()
        for (name,) in schemas:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(name)))
        conn.execute("CREATE SCHEMA public")


@pytest.fixture(scope="session")
def _postgres_server() -> Iterator[str]:
    shpyx.run(["docker", "compose", "-f", str(_COMPOSE_FILE), "up", "-d"])
    try:
        _wait_until_ready(_ADMIN_DSN)
        yield _ADMIN_DSN
    finally:
        shpyx.run(["docker", "compose", "-f", str(_COMPOSE_FILE), "down", "-v"])


@pytest.fixture(scope="session")
def _databases(_postgres_server: str) -> tuple[str, str]:
    # Reset all: create the source and target databases fresh at session start.
    _recreate_database(_postgres_server, _SRC_DB)
    _recreate_database(_postgres_server, _DST_DB)
    return (
        make_conninfo(_postgres_server, dbname=_SRC_DB),
        make_conninfo(_postgres_server, dbname=_DST_DB),
    )


@pytest.fixture
def gen_setup(_databases: tuple[str, str]) -> GenerateSetup:
    # Clear between tests: wipe both databases' schemas before each test.
    src_dsn, dst_dsn = _databases
    _clear(src_dsn)
    _clear(dst_dsn)
    return GenerateSetup(db_src=Db(src_dsn), db_dst=Db(dst_dsn))
