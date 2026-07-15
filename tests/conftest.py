import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import shpyx

from pgmig._db import DbConnection
from tests._api.generate_setup import GenerateSetup
from tests.fixtures.db_utils import ADMIN_DB_DSN, get_unique_postgres_name

_COMPOSE_FILE_DIR = Path(__file__).parent


def pytest_addoption(parser: pytest.Parser) -> None:
    """
    Custom pytest options
    """
    parser.addoption(
        "--stop-docker",
        action="store_true",
        default=False,
        help="Tear down the docker compose stack after the test session (default: leave it running).",
    )
    parser.addoption(
        "--pg-version",
        action="store",
        default=None,
        help=(
            "Postgres major version to test against (e.g. 14). "
            "Falls back to the PGMIG_TEST_PG_VERSION env var, then 18."
        ),
    )


@pytest.fixture(scope="session")
def _unique_key() -> str:
    """
    Get a unique identifier for the current test session.
    """
    result = shpyx.run("git rev-parse --abbrev-ref HEAD", verify_return_code=False)
    branch = result.stdout.strip()
    if result.return_code == 0 and branch and branch != "HEAD":
        return branch

    # Default if git branch is not available.
    return "unknown"


@pytest.fixture(scope="session")
async def _admin_conn(request: pytest.FixtureRequest) -> Iterator[DbConnection]:
    """
    Session level database server plus a shared connection to the admin
    database, reused to (re)create the per-test databases.
    """
    # Resolve the Postgres major version: --pg-version, then PGMIG_TEST_PG_VERSION, then 18.
    # Export it so the docker compose image tag (postgres:${PGMIG_TEST_PG_VERSION}) resolves;
    # the subprocess inherits this environment.
    pg_version = request.config.getoption("--pg-version") or os.environ.get("PGMIG_TEST_PG_VERSION") or "18"
    os.environ["PGMIG_TEST_PG_VERSION"] = pg_version

    # Start the database server.
    shpyx.run("docker compose up -d", exec_dir=_COMPOSE_FILE_DIR)

    # Open a single connection to the admin database for the whole session.
    admin_conn = DbConnection(dsn=ADMIN_DB_DSN)

    async with DbConnection.connect(ADMIN_DB_DSN) as admin_conn:
        yield admin_conn

    # Stop the database server, unless asked to leave it running.
    # Keeping it running is useful when developing locally and running tests frequently.
    if request.config.getoption("--stop-docker"):
        shpyx.run("docker compose down -v", exec_dir=_COMPOSE_FILE_DIR)


@pytest.fixture(scope="function")
async def gen_setup(
    _admin_conn: DbConnection,
    _unique_key: str,
) -> Iterator[GenerateSetup]:
    """
    Main fixture for testing `generate`.
    """
    src_db_name = get_unique_postgres_name("pgmig_src", _unique_key)
    dst_db_name = get_unique_postgres_name("pgmig_dst", _unique_key)

    # Recreate the DBs before each test.
    await _admin_conn.recreate_database()
    await _admin_conn.recreate_database()

    # Create DB connections and yield for the test.
    async with DbConnection(src_db_name) as src_conn:
        async with DbConnection(dst_db_name) as dst_conn:
            yield GenerateSetup(src_conn=src_conn, dst_conn=dst_conn, unique_key=_unique_key)
