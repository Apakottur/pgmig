from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor

from pgmig._build._engine import build_db_info
from pgmig._diff._core import Context
from pgmig._diff._engine import generate_migration_sql


def generate(
    *,
    source: str,
    target: str,
    index_concurrently: bool = False,
    ignore_extension_version: Sequence[str] = (),
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
    """
    # Introspect both databases concurrently.
    with ThreadPoolExecutor(max_workers=2) as executor:
        source_future = executor.submit(build_db_info, source)
        target_future = executor.submit(build_db_info, target)
        source_db_info = source_future.result()
        target_db_info = target_future.result()

    # Generate migration SQL.
    return generate_migration_sql(
        ctx=Context(
            source=source_db_info,
            target=target_db_info,
            index_concurrently=index_concurrently,
            ignore_extension_version=ignore_extension_version,
        )
    )
