import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
import shpyx
import tenacity
from psycopg import sql
from psycopg.conninfo import make_conninfo

_COMPOSE_FILE = Path(__file__).parent / "docker-compose.yml"
_ADMIN_DSN = "postgresql://pgmig:pgmig@localhost:55432/pgmig"


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


@pytest.fixture(scope="session")
def postgres_server() -> Iterator[str]:
    shpyx.run(["docker", "compose", "-f", str(_COMPOSE_FILE), "up", "-d"])
    try:
        _wait_until_ready(_ADMIN_DSN)
        yield _ADMIN_DSN
    finally:
        shpyx.run(["docker", "compose", "-f", str(_COMPOSE_FILE), "down", "-v"])


@pytest.fixture
def db_pair(postgres_server: str) -> Iterator[tuple[str, str]]:
    admin_dsn = postgres_server
    suffix = uuid.uuid4().hex
    src_name = f"pgmig_src_{suffix}"
    tgt_name = f"pgmig_tgt_{suffix}"
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(src_name)))
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(tgt_name)))
    src_dsn = make_conninfo(admin_dsn, dbname=src_name)
    tgt_dsn = make_conninfo(admin_dsn, dbname=tgt_name)
    try:
        yield src_dsn, tgt_dsn
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(src_name)))
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(tgt_name)))
