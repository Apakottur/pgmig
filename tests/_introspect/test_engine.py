import asyncio
import time
from typing import Any

import pytest
from pytest_mock import MockerFixture

from pgmig import PgmigDbIdleTimeoutError
from pgmig._db import DbReadOnlyConnection
from pgmig._drivers import DbConnInfo, DbDriver
from pgmig._introspect import default_privileges
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
    Ensure that the snapshot transaction ends before the last batch of rows is processed, so that slow processing
    does not trip the server's idle_in_transaction_session_timeout.
    """
    process_rows = default_privileges.DefaultPrivilegesLoader.process_rows

    # Process the rows of the last loader slower than the server's idle limit.
    def slow_process_rows(rows: list[Any]) -> None:
        time.sleep(0.5)
        process_rows(rows)

    mocker.patch.object(default_privileges.DefaultPrivilegesLoader, "process_rows", side_effect=slow_process_rows)

    async with idle_in_transaction_timeout(gen_setup.src, gen_setup.src_db_name, timeout_ms=100):
        info = await introspect_db(db_conn_info=gen_setup.src.db_conn_info)

    assert "public" in info.schema_by_name


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
            await read_only_conn.introspect(["SELECT 1"], end_snapshot=False)

            # Sit idle in the snapshot transaction past the server's limit.
            await asyncio.sleep(0.5)

            await read_only_conn.introspect(["SELECT 1"], end_snapshot=False)

    async with idle_in_transaction_timeout(gen_setup.src, gen_setup.src_db_name, timeout_ms=100):
        with pytest.raises(PgmigDbIdleTimeoutError, match=r"source database.*idle_in_transaction_session_timeout"):
            await introspect_after_idling()
