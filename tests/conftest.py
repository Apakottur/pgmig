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
    parser.addoption(
        "--stop-docker",
        action="store_true",
        default=False,
        help="Tear down the docker compose stack after the test session (default: leave it running).",
    )


@pytest.fixture(scope="session", autouse=True)
def _postgres_server(request: pytest.FixtureRequest) -> Iterator[str]:
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
        # Stop the database server, unless asked to leave it running.
        if request.config.getoption("--stop-docker"):
            shpyx.run("docker compose down -v", exec_dir=_COMPOSE_FILE_DIR)


@pytest.fixture(scope="function")
def gen_setup(_postgres_server: str) -> GenerateSetup:
    """
    Main fixture for testing `generate`.
    """
    # Create the source and target databases.
    src_conn = DbConnection(_SRC_DB)
    dst_conn = DbConnection(_DST_DB)

    # Provide the utility class for the test
    return GenerateSetup(src_conn, dst_conn)
