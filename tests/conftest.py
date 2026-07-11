import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
import shpyx
from psycopg import sql
from psycopg.conninfo import make_conninfo

_COMPOSE_FILE = Path(__file__).parent / "docker-compose.yml"
_ADMIN_DSN = "postgresql://pgmig:pgmig@localhost:55432/pgmig"


@pytest.fixture(scope="session")
def postgres_server() -> Iterator[str]:
    shpyx.run(["docker", "compose", "-f", str(_COMPOSE_FILE), "up", "-d", "--wait"])
    try:
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
