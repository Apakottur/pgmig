import asyncio
from collections.abc import Sequence

from pgmig._diff._engine import get_diff
from pgmig._introspect._engine import introspect_db


async def agenerate(
    *,
    source: str,
    target: str,
    index_concurrently: bool = False,
    ignore_extension_version: Sequence[str] = (),
    ignore_owner: bool = False,
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
        ignore_owner: Suppress all ALTER ... OWNER TO statements.
    """
    # Introspect both databases concurrently.
    source_result, target_result = await asyncio.gather(introspect_db(source), introspect_db(target))

    # Generate migration SQL.
    return get_diff(
        source=source_result,
        target=target_result,
        index_concurrently=index_concurrently,
        ignore_extension_version=ignore_extension_version,
        ignore_owner=ignore_owner,
    )


def generate(
    *,
    source: str,
    target: str,
    index_concurrently: bool = False,
    ignore_extension_version: Sequence[str] = (),
    ignore_owner: bool = False,
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
        ignore_owner: Suppress all ALTER ... OWNER TO statements.
    """
    return asyncio.run(
        agenerate(
            source=source,
            target=target,
            index_concurrently=index_concurrently,
            ignore_extension_version=ignore_extension_version,
            ignore_owner=ignore_owner,
        )
    )
