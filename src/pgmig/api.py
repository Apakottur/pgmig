from concurrent.futures import ThreadPoolExecutor

from pgmig._build._engine import build_db_info
from pgmig._diff._core import Options
from pgmig._diff._engine import generate_migration_sql


def generate(*, source: str, target: str, index_concurrently: bool = False) -> str:
    """
    Generate the migration SQL between the given source and target databases.

    index_concurrently: emit CREATE/DROP INDEX (including CREATE UNIQUE INDEX) with
        CONCURRENTLY. The resulting statements cannot run inside a transaction block.
    """
    # Introspect both databases concurrently.
    with ThreadPoolExecutor(max_workers=2) as executor:
        source_future = executor.submit(build_db_info, source)
        target_future = executor.submit(build_db_info, target)
        source_db_info = source_future.result()
        target_db_info = target_future.result()

    # Generate migration SQL.
    options = Options(index_concurrently=index_concurrently)
    return generate_migration_sql(source=source_db_info, target=target_db_info, options=options)
