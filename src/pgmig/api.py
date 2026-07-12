from concurrent.futures import ThreadPoolExecutor

from pgmig._build._engine import build_db_info
from pgmig._diff._engine import generate_migration_sql


def generate(*, source: str, target: str) -> str:
    """
    Generate the migration SQL between the given source and target databases.
    """
    # Introspect both databases concurrently.
    with ThreadPoolExecutor(max_workers=2) as executor:
        source_future = executor.submit(build_db_info, source)
        target_future = executor.submit(build_db_info, target)
        source_db_info = source_future.result()
        target_db_info = target_future.result()

    # Generate migration SQL.
    return generate_migration_sql(source=source_db_info, target=target_db_info)
