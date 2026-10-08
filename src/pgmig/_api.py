import asyncio
from collections.abc import Sequence

from pgmig._db import DbConnInfo
from pgmig._diff._engine import get_diff
from pgmig._drivers import DbDriver
from pgmig._errors import PgmigApiError, PgmigDbConnectionError, PgmigDbDriverError
from pgmig._introspect._engine import introspect_db


async def agenerate(
    *,
    source: str,
    target: str,
    index_concurrently: bool = False,
    safe_not_null: bool = False,
    ignore_extension_version: Sequence[str] = (),
    ignore_schemas: Sequence[str] = (),
    include_owner: bool = False,
    include_grants: bool = False,
    driver: DbDriver = DbDriver.AUTO,
) -> str:
    """
    Generate the migration SQL between the given source and target databases.

    Args:
        source: The source database DSN.
        target: The target database DSN.
        index_concurrently: Whether to emit CREATE/DROP INDEX (including CREATE UNIQUE INDEX) with CONCURRENTLY.
                            Using CONCURRENTLY avoids blocking index read/write operations, but takes longer to execute
                            and cannot be run inside a transaction block.
        safe_not_null: Whether to emit SET NOT NULL on an existing column through a CHECK (col IS NOT NULL)
                       constraint that is added NOT VALID, validated, and dropped once the column is NOT NULL.
                       The validated CHECK lets SET NOT NULL skip its full-table scan, so the ACCESS EXCLUSIVE
                       lock is held only briefly. Run the statements outside a transaction block, otherwise the
                       lock taken by the first one is held throughout.
        ignore_extension_version: Names of extensions whose version mismatch is ignored: no ALTER EXTENSION ...
                                  UPDATE TO is emitted for them. Empty (default) ignores none.
        ignore_schemas: Schema names to exclude from the diff entirely -- their tables and every other object,
                        and the create/drop of the schema itself, are ignored. Empty (default) ignores none.
        include_owner: Emit ALTER ... OWNER TO statements to reconcile ownership. Off by default: ownership
                       references cluster-level roles that routinely differ across environments, so it is not
                       part of the default convergence.
        include_grants: Also emit named-role GRANT / REVOKE. PUBLIC grants are always diffed;
                        named-role grants (role-dependent, may fail at apply) are opt-in.
        driver: The database driver to connect with. AUTO (default) lets pgmig pick among the
                supported drivers; naming one pins it.
    """
    # Introspect both databases concurrently. Collect all failures instead of raising them.
    source_result, target_result = await asyncio.gather(
        introspect_db(
            db_conn_info=DbConnInfo(dsn=source, label="source", driver=driver), ignore_schemas=ignore_schemas
        ),
        introspect_db(
            db_conn_info=DbConnInfo(dsn=target, label="target", driver=driver), ignore_schemas=ignore_schemas
        ),
        return_exceptions=True,
    )

    # DB Driver errors.
    source_driver_error = source_result if isinstance(source_result, PgmigDbDriverError) else None
    target_driver_error = target_result if isinstance(target_result, PgmigDbDriverError) else None
    if source_driver_error is not None or target_driver_error is not None:
        raise PgmigDbConnectionError(source_error=source_driver_error, target_error=target_driver_error)

    # Other errors.
    if isinstance(source_result, BaseException):
        raise source_result
    if isinstance(target_result, BaseException):
        raise target_result

    # No errors - generate migration SQL.
    return get_diff(
        source=source_result,
        target=target_result,
        index_concurrently=index_concurrently,
        safe_not_null=safe_not_null,
        ignore_extension_version=ignore_extension_version,
        include_owner=include_owner,
        include_grants=include_grants,
    )


def generate(
    *,
    source: str,
    target: str,
    index_concurrently: bool = False,
    safe_not_null: bool = False,
    ignore_extension_version: Sequence[str] = (),
    ignore_schemas: Sequence[str] = (),
    include_owner: bool = False,
    include_grants: bool = False,
    driver: DbDriver = DbDriver.AUTO,
) -> str:
    """
    Synchronous equivalent of [`agenerate`][pgmig.agenerate], which documents the arguments.

    Raises:
        PgmigApiError: If called from within a running event loop. This synchronous wrapper
                       drives its own loop via [`asyncio.run`][asyncio.run], which cannot nest;
                       call [`agenerate`][pgmig.agenerate] and await it instead.
    """
    # Verify that we're not already in an asyncio context.
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise PgmigApiError("generate() cannot be called from within a running event loop. Use agenerate() instead.")

    return asyncio.run(
        agenerate(
            source=source,
            target=target,
            index_concurrently=index_concurrently,
            safe_not_null=safe_not_null,
            ignore_extension_version=ignore_extension_version,
            ignore_schemas=ignore_schemas,
            include_owner=include_owner,
            include_grants=include_grants,
            driver=driver,
        )
    )
