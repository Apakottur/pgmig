from pgmig._introspect._engine import introspect_db
from tests._api.generate_setup import GenerateSetup
from tests.fixtures.db_utils import wait_until_accepting_connections


async def test_introspection_through_pgbouncer(gen_setup: GenerateSetup) -> None:
    """
    Ensure that introspection works through pgbouncer.
    """
    # Create an object on the source database over a direct connection.
    gen_setup.src.execute("CREATE TABLE widget (id integer)")

    # Wait for pgbouncer to start accepting connections.
    wait_until_accepting_connections(gen_setup.src.pgbouncer_dsn)

    # Introspect the database through pgbouncer.
    info = await introspect_db(gen_setup.src.pgbouncer_dsn)

    # Verify the introspection result.
    assert "widget" in info.schema_by_name["public"].table_by_name
