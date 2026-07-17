from pgmig._db import DbReadOnlyConnection
from tests._api.generate_setup import GenerateSetup


async def test_read_only_snapshot_pins_one_view(gen_setup: GenerateSetup) -> None:
    """
    Reads inside DbReadOnlyConnection.snapshot() share one REPEATABLE READ snapshot: a table
    another connection creates and commits mid-snapshot stays invisible to it. This is what
    lets the introspection loaders see a single consistent view of the database; without the
    enclosing transaction each query would take its own snapshot (autocommit makes the
    REPEATABLE READ isolation level a no-op on its own).
    """
    probe = "SELECT count(*) FROM pg_class WHERE relname = 'snap_probe'"
    async with DbReadOnlyConnection.connect(dsn=gen_setup.src.dsn) as read_only, read_only.snapshot():
        before = await read_only.execute(probe)
        # A separate (autocommit) connection creates and commits the table mid-snapshot.
        await gen_setup.src.execute("CREATE TABLE snap_probe (x int)")
        after = await read_only.execute(probe)

    assert before == [(0,)]
    assert after == [(0,)], "snapshot leaked a concurrently-created table -> reads not on one snapshot"
