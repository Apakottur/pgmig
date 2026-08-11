import asyncio
from collections.abc import Sequence

from pgmig._db import DbConnInfo
from pgmig._diff._engine import get_diff
from pgmig._drivers import DbDriver
from pgmig._errors import DbConnectionError, DbDriverError, PgmigApiError
from pgmig._introspect._engine import introspect_db


async def agenerate(
    *,
    source: str,
    target: str,
    index_concurrently: bool = False,
    ignore_extension_version: Sequence[str] = (),
    ignore_schemas: Sequence[str] = (),
    include_owner: bool = False,
    include_grants: bool = False,
    driver: DbDriver = DbDriver.AUTO,
) -> str:
    """
    Asynchronous equivalent of [`generate`][pgmig.generate].

    Args:
        source: The source database DSN.
        target: The target database DSN.
        index_concurrently: Whether to emit CREATE/DROP INDEX (including CREATE UNIQUE INDEX) with CONCURRENTLY.
                            Using CONCURRENTLY avoids blocking index read/write operations, but takes longer to execute
                            and cannot be run inside a transaction block.
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

    # Determine the outcome of the run.
    match (source_result, target_result):
        # DB Driver errors.
        case (DbDriverError(), DbDriverError()):
            raise DbConnectionError(
                source_error=source_result.driver_error,
                target_error=target_result.driver_error,
            )
        case (DbDriverError(), _):
            raise DbConnectionError(source_error=source_result.driver_error, target_error=None)
        case (_, DbDriverError()):
            raise DbConnectionError(source_error=None, target_error=target_result.driver_error)
        # Other errors.
        case (BaseException(), _):
            raise source_result
        case (_, BaseException()):
            raise target_result
        # No errors - generate migration SQL. ty does not narrow through match patterns, so
        # it still sees the union asyncio.gather returns for each result here.
        case _:
            return get_diff(
                source=source_result,  # ty: ignore[invalid-argument-type]
                target=target_result,  # ty: ignore[invalid-argument-type]
                index_concurrently=index_concurrently,
                ignore_extension_version=ignore_extension_version,
                include_owner=include_owner,
                include_grants=include_grants,
            )


def generate(
    *,
    source: str,
    target: str,
    index_concurrently: bool = False,
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
            ignore_extension_version=ignore_extension_version,
            ignore_schemas=ignore_schemas,
            include_owner=include_owner,
            include_grants=include_grants,
            driver=driver,
        )
    )
