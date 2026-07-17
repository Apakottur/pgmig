from pgmig._db import DbReadOnlyConnection
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
    info = await introspect_db(dsn=pgbouncer_dsn)

    # Verify the introspection result.
    assert "widget" in info.schema_by_name["public"].table_by_name


async def test_read_only_snapshot_pins_one_view(gen_setup: GenerateSetup) -> None:
    """
    Ensure that introspection is done on a single snapshot of the DB.
    """
    probe = "SELECT count(*) FROM pg_class WHERE relname = 'snap_probe'"

    async with DbReadOnlyConnection.connect(dsn=gen_setup.src.dsn) as read_only_conn:
        # Run the probe before the table is created.
        before = await read_only_conn.execute(probe)

        # Create the table on a separate (auto-committed) connection.
        await gen_setup.src.execute("CREATE TABLE snap_probe (x int)")

        # Run the probe after the table is created.
        after = await read_only_conn.execute(probe)

    # The table should not be visible to the read-only connection, both before and after the table is created.
    assert before == [(0,)]
    assert after == [(0,)], "snapshot leaked a concurrently-created table -> reads not on one snapshot"
