import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import shpyx

from pgmig._db import DEFAULT_DRIVER, DbConnection, Driver
from tests._api.generate_setup import GenerateSetup
from tests.fixtures.db_utils import get_dsn, get_unique_postgres_name, recreate_database, wait_for_db_connection

_VALID_DRIVERS = ("psycopg", "asyncpg")

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
    parser.addoption(
        "--driver",
        action="store",
        default=None,
        choices=_VALID_DRIVERS,
        help=(
            f"Database driver to test against ({' or '.join(_VALID_DRIVERS)}). "
            f"Falls back to the PGMIG_DRIVER env var, then {DEFAULT_DRIVER!r}."
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
def _driver(request: pytest.FixtureRequest) -> Driver:
    """
    Get the database driver under test ("psycopg" or "asyncpg").
    """
    config_option = request.config.getoption("--driver")
    env_var = os.environ.get("PGMIG_DRIVER")

    # Resolve the final driver: --driver, then PGMIG_DRIVER, then the default.
    final_driver: Driver = config_option or env_var or DEFAULT_DRIVER

    # Export it so CLI invocations (which read PGMIG_DRIVER) use the same driver.
    os.environ["PGMIG_DRIVER"] = final_driver

    return final_driver


@pytest.fixture(scope="session")
async def _admin_conn(request: pytest.FixtureRequest, _driver: Driver) -> AsyncIterator[DbConnection]:
    """
    Session level database server plus a shared connection to the admin
    database, reused to (re)create the per-test databases.
    """
    # Start the database server.
    shpyx.run("docker compose up -d", exec_dir=_COMPOSE_FILE_DIR)

    # Get the database DSN.
    admin_db_dsn = get_dsn("postgres")

    # Wait for the database server to be ready.
    await wait_for_db_connection(dsn=admin_db_dsn, driver=_driver)

    # Open a single connection to the admin database for the whole session.
    async with DbConnection.connect(dsn=admin_db_dsn, driver=_driver) as admin_conn:
        yield admin_conn

    # Stop the database server, unless asked to leave it running.
    # Keeping it running is useful when developing locally and running tests frequently.
    if request.config.getoption("--stop-docker"):
        shpyx.run("docker compose down -v", exec_dir=_COMPOSE_FILE_DIR)


@pytest.fixture(scope="function")
async def gen_setup(
    _unique_key: str,
    _pg_major: int,
    _driver: Driver,
    _admin_conn: DbConnection,
) -> AsyncIterator[GenerateSetup]:
    """
    Main fixture for testing `generate`.
    """
    # Get the database names and DSNs.
    src_db_name = get_unique_postgres_name("pgmig_src", _unique_key)
    dst_db_name = get_unique_postgres_name("pgmig_dst", _unique_key)
    src_db_dsn = get_dsn(src_db_name)
    dst_db_dsn = get_dsn(dst_db_name)

    # Recreate the DBs before each test.
    await recreate_database(_admin_conn, src_db_name)
    await recreate_database(_admin_conn, dst_db_name)

    # Create DB connections and yield for the test.
    async with (
        DbConnection.connect(dsn=src_db_dsn, driver=_driver) as src_conn,
        DbConnection.connect(dsn=dst_db_dsn, driver=_driver) as dst_conn,
    ):
        yield GenerateSetup(
            src_db_name=src_db_name,
            dst_db_name=dst_db_name,
            src_conn=src_conn,
            dst_conn=dst_conn,
            pg_major=_pg_major,
            driver=_driver,
            unique_key=_unique_key,
        )
