from pgmig._introspect._engine import introspect_db
from tests._api.generate_setup import GenerateSetup
from tests.fixtures.db_utils import get_dsn


async def test_introspection_through_pgbouncer(gen_setup: GenerateSetup) -> None:
    """
    Ensure that introspection works through pgbouncer.
    """
    # Create an object on the source database over a direct connection.
    await gen_setup.src.execute("CREATE TABLE widget (id integer)")

    # Introspect the database through pgbouncer.
    pgbouncer_dsn = get_dsn(gen_setup.src_db_name, pgbouncer=True)
    info = await introspect_db(pgbouncer_dsn, gen_setup.driver)

    # Verify the introspection result.
    assert "widget" in info.schema_by_name["public"].table_by_name
