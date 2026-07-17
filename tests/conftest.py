import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import shpyx

from pgmig._db import DbConnection
from tests._api.generate_setup import GenerateSetup
from tests.fixtures.db_utils import (
    get_dsn,
    get_unique_postgres_name,
    recreate_database,
    reset_database,
    wait_for_db_connection,
)

_COMPOSE_FILE_DIR = Path(__file__).parent


def pytest_addoption(parser: pytest.Parser) -> None:
    """
    Custom pytest options.
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
    # Generate a unique key from the git branch.
    result = shpyx.run("git rev-parse --abbrev-ref HEAD", verify_return_code=False)
    branch = result.stdout.strip()
    if result.return_code == 0 and branch and branch != "HEAD":
        return branch

    # Default if git branch is not available.
    return "unknown"


@pytest.fixture(scope="session")
def _pg_major(request: pytest.FixtureRequest) -> int:
    """
    Get the Postgres major version of the server under test (e.g. 16).
    """
    config_option = request.config.getoption("--pg-version")
    env_var = os.environ.get("PGMIG_TEST_PG_VERSION")

    # Construct the final Postgres major version.
    final_pg_version = config_option or env_var or "18"

    # Export it so that docker compose has it.
    os.environ["PGMIG_TEST_PG_VERSION"] = final_pg_version

    # Return it.
    return int(final_pg_version)


@pytest.fixture(scope="session")
async def _admin_conn(request: pytest.FixtureRequest) -> AsyncIterator[DbConnection]:
    """
    Session level database server plus a shared connection to the admin
    database, reused to (re)create the per-test databases.
    """
    # Start the database server.
    shpyx.run("docker compose up -d", exec_dir=_COMPOSE_FILE_DIR)

    # Get the database DSN.
    admin_db_dsn = get_dsn("postgres")

    # Wait for the database server to be ready.
    await wait_for_db_connection(dsn=admin_db_dsn)

    # Open a single connection to the admin database for the whole session.
    async with DbConnection.connect(dsn=admin_db_dsn) as admin_conn:
        yield admin_conn

    # Stop the database server, unless asked to leave it running.
    # Keeping it running is useful when developing locally and running tests frequently.
    if request.config.getoption("--stop-docker"):
        shpyx.run("docker compose down -v", exec_dir=_COMPOSE_FILE_DIR)


@pytest.fixture(scope="session")
async def _persistent_dbs(
    _unique_key: str,
    _admin_conn: DbConnection,
) -> AsyncIterator[tuple[str, str, DbConnection, DbConnection]]:
    """
    Create the source and target databases once for the whole session and hold a connection
    open to each. Tests reset these to empty (see `gen_setup`) rather than paying a
    DROP/CREATE DATABASE and reconnect per test.
    """
    src_db_name = get_unique_postgres_name("pgmig_src", _unique_key)
    dst_db_name = get_unique_postgres_name("pgmig_dst", _unique_key)

    # Create the DBs.
    await recreate_database(_admin_conn, src_db_name)
    await recreate_database(_admin_conn, dst_db_name)

    async with (
        DbConnection.connect(dsn=get_dsn(src_db_name)) as src_conn,
        DbConnection.connect(dsn=get_dsn(dst_db_name)) as dst_conn,
    ):
        yield src_db_name, dst_db_name, src_conn, dst_conn


@pytest.fixture(scope="function")
async def gen_setup(
    _unique_key: str,
    _pg_major: int,
    _persistent_dbs: tuple[str, str, DbConnection, DbConnection],
) -> GenerateSetup:
    """
    Main fixture for testing `generate`. The databases are reset (not recreated) and their
    connections outlive the test, so there is no teardown -- this fixture returns rather than
    yields.
    """
    src_db_name, dst_db_name, src_conn, dst_conn = _persistent_dbs

    # Reset the persistent DBs to empty before each test.
    await reset_database(src_conn)
    await reset_database(dst_conn)

    return GenerateSetup(
        src_db_name=src_db_name,
        dst_db_name=dst_db_name,
        src_conn=src_conn,
        dst_conn=dst_conn,
        pg_major=_pg_major,
        unique_key=_unique_key,
    )
