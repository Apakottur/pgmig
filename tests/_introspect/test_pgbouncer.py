import psycopg
import tenacity

from pgmig._introspect._engine import introspect_db
from tests._api.generate_setup import GenerateSetup


@tenacity.retry(wait=tenacity.wait_fixed(0.5), stop=tenacity.stop_after_delay(15), reraise=True)
def _wait_for_pgbouncer(dsn: str) -> None:
    """
    Wait until pgbouncer is accepting connections (it starts alongside Postgres).
    """
    psycopg.connect(dsn).close()


def test_introspection_through_pgbouncer(gen_setup: GenerateSetup) -> None:
    """
    Ensure that introspection works through pgbouncer.
    """
    # Create an object on the source database over a direct connection.
    gen_setup.src.execute("CREATE TABLE widget (id integer)")

    # Wait for pgbouncer to start accepting connections.
    _wait_for_pgbouncer(gen_setup.src.pgbouncer_dsn)

    # Introspect the database through pgbouncer.
    info = introspect_db(gen_setup.src.pgbouncer_dsn)

    # Verify the introspection result.
    assert "widget" in info.schema_by_name["public"].table_by_name
