import asyncio
from collections.abc import Sequence

from pgmig._diff._engine import get_diff
from pgmig._errors import PgmigApiError
from pgmig._introspect._engine import introspect_db


async def agenerate(
    *,
    source: str,
    target: str,
    index_concurrently: bool = False,
    ignore_extension_version: Sequence[str] = (),
    include_owner: bool = False,
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
        include_owner: Emit ALTER ... OWNER TO statements to reconcile ownership. Off by default: ownership
                       references cluster-level roles that routinely differ across environments, so it is not
                       part of the default convergence.
    """
    # Introspect both databases concurrently.
    source_result, target_result = await asyncio.gather(introspect_db(source), introspect_db(target))

    # Generate migration SQL.
    return get_diff(
        source=source_result,
        target=target_result,
        index_concurrently=index_concurrently,
        ignore_extension_version=ignore_extension_version,
        include_owner=include_owner,
    )


def generate(
    *,
    source: str,
    target: str,
    index_concurrently: bool = False,
    ignore_extension_version: Sequence[str] = (),
    include_owner: bool = False,
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
        include_owner: Emit ALTER ... OWNER TO statements to reconcile ownership. Off by default: ownership
                       references cluster-level roles that routinely differ across environments, so it is not
                       part of the default convergence.

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
            include_owner=include_owner,
        )
    )
