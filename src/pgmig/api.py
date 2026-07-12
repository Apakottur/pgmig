from concurrent.futures import ThreadPoolExecutor

from pgmig._build._engine import build_db_info
from pgmig._diff._core import Options
from pgmig._diff._engine import generate_migration_sql


def generate(*, source: str, target: str, ignore_extension_version: bool | list[str] = False) -> str:
    """
    Generate the migration SQL between the given source and target databases.

    ignore_extension_version suppresses the ALTER EXTENSION ... UPDATE TO emitted for an
    extension whose version differs between the databases: True ignores every extension,
    a list of names ignores only those, and False (default) ignores none.
    """
    # Introspect both databases concurrently.
    with ThreadPoolExecutor(max_workers=2) as executor:
        source_future = executor.submit(build_db_info, source)
        target_future = executor.submit(build_db_info, target)
        source_db_info = source_future.result()
        target_db_info = target_future.result()

    # Generate migration SQL.
    options = Options(ignore_extension_version=ignore_extension_version)
    return generate_migration_sql(source=source_db_info, target=target_db_info, options=options)
