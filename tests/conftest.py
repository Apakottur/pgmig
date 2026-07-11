from collections.abc import Iterator
from pathlib import Path

import pytest
import shpyx

from tests.fixtures.generate_setup import GenerateSetup
from tests.utils.db_utils import DbConnection

_COMPOSE_FILE_DIR = Path(__file__).parent

_SRC_DB = "pgmig_src"
_DST_DB = "pgmig_dst"


@pytest.fixture(scope="session", autouse=True)
def _postgres_server() -> Iterator[str]:
    """
    Session level database server.
    """
    # Start the database server.
    shpyx.run("docker compose up -d", exec_dir=_COMPOSE_FILE_DIR)

    # Create a connection to the admin database.
    admin_db_conn = DbConnection("postgres")

    try:
        yield admin_db_conn.dsn
    finally:
        # Stop the database server.
        shpyx.run("docker compose down -v", exec_dir=_COMPOSE_FILE_DIR)


@pytest.fixture(scope="session", autouse=True)
def _databases(_postgres_server: str) -> tuple[DbConnection, DbConnection]:
    """
    Session level database configuration.
    """
    # Create the source and target databases (once per session).
    src_conn = DbConnection(_SRC_DB)
    dst_conn = DbConnection(_DST_DB)
    return src_conn, dst_conn


@pytest.fixture(scope="function")
def gen_setup(_databases: tuple[DbConnection, DbConnection]) -> GenerateSetup:
    """
    Main fixture for testing `generate`.
    """
    # Get the source and target database DSNs.
    src_conn, dst_conn = _databases

    # Clear between tests: wipe both databases' schemas before each test.
    src_conn.reset()
    dst_conn.reset()

    # Provide the utility class for the test
    return GenerateSetup(src_conn, dst_conn)
