from collections.abc import Iterator
from pathlib import Path

import pytest
import shpyx

from tests.fixtures.generate_setup import GenerateSetup
from tests.utils.db_utils import DbConnection

_COMPOSE_FILE_DIR = Path(__file__).parent

_SRC_DB = "pgmig_src"
_DST_DB = "pgmig_dst"


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


@pytest.fixture(scope="session", autouse=True)
def _admin_conn(request: pytest.FixtureRequest) -> Iterator[DbConnection]:
    """
    Session level database server plus a shared connection to the admin
    database, reused to (re)create the per-test databases.
    """
    # Start the database server.
    shpyx.run("docker compose up -d postgres", exec_dir=_COMPOSE_FILE_DIR)

    # Open a single connection to the admin database for the whole session.
    admin_conn = DbConnection("postgres")

    try:
        yield admin_conn
    finally:
        admin_conn.close()

        # Stop the database server, unless asked to leave it running.
        # Keeping it running is useful when developing locally and running tests frequently.
        if request.config.getoption("--stop-docker"):
            shpyx.run("docker compose down -v", exec_dir=_COMPOSE_FILE_DIR)


@pytest.fixture(scope="function")
def gen_setup(_admin_conn: DbConnection) -> Iterator[GenerateSetup]:
    """
    Main fixture for testing `generate`.
    """
    # Create the source and target databases via the shared admin connection.
    src_conn = DbConnection(_SRC_DB, admin_conn=_admin_conn)
    dst_conn = DbConnection(_DST_DB, admin_conn=_admin_conn)

    # Provide the utility class for the test.
    try:
        yield GenerateSetup(src_conn, dst_conn)
    finally:
        src_conn.close()
        dst_conn.close()
