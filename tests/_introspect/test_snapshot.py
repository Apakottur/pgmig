from pgmig._db import DbReadOnlyConnection
from tests._api.generate_setup import GenerateSetup
from tests.fixtures.db_utils import get_dsn


async def test_introspection_holds_single_snapshot(gen_setup: GenerateSetup) -> None:
    """
    Every introspection query must observe one snapshot of the database, so concurrent DDL
    cannot tear the result (an object present for tables.sql but gone by constraints.sql).

    Read a marker table's presence on a read-only introspection connection, commit a DROP
    from a separate connection mid-way, then read again: the second read must still see the
    table. Under an autocommit connection each query takes its own snapshot and the second
    read sees the drop (torn); the fix runs all reads in one REPEATABLE READ transaction.
    """
    await gen_setup.src.execute("CREATE TABLE snap_marker (id integer)")
    probe = "SELECT count(*) FROM pg_class WHERE relname = 'snap_marker'"

    async with DbReadOnlyConnection.connect(dsn=get_dsn(gen_setup.src_db_name)) as ro_conn:
        ((before,),) = await ro_conn.execute(probe)
        # Concurrent DDL, committed by another connection, in the middle of introspection.
        await gen_setup.src.execute("DROP TABLE snap_marker")
        ((after,),) = await ro_conn.execute(probe)

    assert before == 1
    assert after == 1, "introspection connection did not hold a single snapshot across queries"
