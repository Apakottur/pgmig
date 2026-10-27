from collections.abc import Sequence
from typing import Any

import pytest
from pytest_mock import MockerFixture

from pgmig import PgmigDbIdleTimeoutError
from pgmig._db import DbReadOnlyConnection
from pgmig._drivers import DbConnInfo, DbDriver
from pgmig._introspect._engine import introspect_db
from tests._api.generate_setup import GenerateSetup
from tests.fixtures.db_utils import get_dsn, idle_in_transaction_timeout


async def test_introspection_through_pgbouncer(gen_setup: GenerateSetup) -> None:
    """
    Ensure that introspection works through pgbouncer.
    """
    # Create an object on the source database over a direct connection.
    await gen_setup.src.execute("CREATE TABLE widget (id integer)")

    # Introspect the database through pgbouncer.
    pgbouncer_dsn = get_dsn(gen_setup.src_db_name, pgbouncer=True)
    info = await introspect_db(db_conn_info=DbConnInfo(dsn=pgbouncer_dsn, label="source"))

    # Verify the introspection result.
    assert "widget" in info.schema_by_name["public"].table_by_name


async def test_read_only_snapshot_pins_one_view(gen_setup: GenerateSetup) -> None:
    """
    Ensure that introspection is done on a single snapshot of the DB.
    """
    probe = "SELECT count(*) FROM pg_class WHERE relname = 'snap_probe'"

    async with DbReadOnlyConnection.connect(db_conn_info=gen_setup.src.db_conn_info) as read_only_conn:
        # Run the probe before the table is created.
        before = await read_only_conn.introspect([probe], end_snapshot=False)

        # Create the table on a separate (auto-committed) connection.
        await gen_setup.src.execute("CREATE TABLE snap_probe (x int)")

        # Run the probe after the table is created.
        after = await read_only_conn.introspect([probe], end_snapshot=False)

    # The table should not be visible to the read-only connection, both before and after the table is created.
    assert before == [[{"count": 0}]]
    assert after == [[{"count": 0}]], "snapshot leaked a concurrently-created table -> reads not on one snapshot"


async def test_read_only_snapshot_settings_apply_to_first_query(gen_setup: GenerateSetup) -> None:
    """
    Ensure that the snapshot transaction settings are in effect from the very first introspection query.
    """
    async with DbReadOnlyConnection.connect(db_conn_info=gen_setup.src.db_conn_info) as read_only_conn:
        [[settings]] = await read_only_conn.introspect(
            [
                "SELECT current_setting('search_path') AS search_path, "
                "current_setting('transaction_read_only') AS read_only, "
                "current_setting('transaction_isolation') AS isolation"
            ],
            end_snapshot=False,
        )

    # The first query should already run with an empty search path, in a read-only REPEATABLE READ transaction.
    assert settings == {"search_path": '""', "read_only": "on", "isolation": "repeatable read"}


async def test_introspection_ends_snapshot_before_processing_rows(
    gen_setup: GenerateSetup, mocker: MockerFixture
) -> None:
    """
    Ensure that the snapshot transaction ends before the last batch of rows is processed, so that it does not sit
    idle (and trip the server's idle_in_transaction_session_timeout) while the rows are processed.
    """
    introspect = DbReadOnlyConnection.introspect
    open_snapshots_after_batch = []

    # After each batch of queries, count the open snapshot transactions on the server, from another connection.
    async def introspect_and_count(
        self: DbReadOnlyConnection, queries: Sequence[str], *, end_snapshot: bool
    ) -> list[list[dict[str, Any]]]:
        rows_per_query = await introspect(self, queries, end_snapshot=end_snapshot)
        [(open_snapshots,)] = await gen_setup.src.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND state = 'idle in transaction'"
        )
        open_snapshots_after_batch.append(open_snapshots)
        return rows_per_query

    mocker.patch.object(DbReadOnlyConnection, "introspect", introspect_and_count)

    await introspect_db(db_conn_info=gen_setup.src.db_conn_info)

    # The snapshot should stay open between the batches, and end with the last one.
    assert open_snapshots_after_batch == [1, 1, 0]


async def test_idle_in_transaction_timeout_error(gen_setup: GenerateSetup) -> None:
    """
    Ensure that a server ending the snapshot transaction for sitting idle raises a pgmig error naming the setting.
    """
    # asyncpg drops the server's termination message when it arrives on an idle connection, and only reports that
    # the connection is closed, so the cause cannot be told apart from any other lost connection.
    if gen_setup.driver.resolved == DbDriver.ASYNCPG:
        pytest.skip("asyncpg does not report why the server ended the connection")

    async def introspect_after_idling() -> None:
        async with DbReadOnlyConnection.connect(db_conn_info=gen_setup.src.db_conn_info) as read_only_conn:
            # Hold an advisory lock in the snapshot transaction.
            await read_only_conn.introspect(["SELECT pg_advisory_xact_lock(1)"], end_snapshot=False)

            # Wait for the lock from another connection. It is released only when the transaction ends, here when
            # the server ends it for sitting idle.
            await gen_setup.src.execute("SELECT pg_advisory_xact_lock(1)")

            await read_only_conn.introspect(["SELECT 1"], end_snapshot=False)

    async with idle_in_transaction_timeout(gen_setup.src, gen_setup.src_db_name, timeout_ms=10):
        with pytest.raises(PgmigDbIdleTimeoutError, match=r"source database.*idle_in_transaction_session_timeout"):
            await introspect_after_idling()
