from pgmig._build import build_db_info
from pgmig._diff._engine import generate_migration_sql


def generate(*, source: str, target: str) -> str:
    """
    Generate the migration SQL between the given source and target databases.
    """
    # Build source database info.
    source_db_info = build_db_info(source)

    # Build target database info.
    target_db_info = build_db_info(target)

    # Generate migration SQL.
    return generate_migration_sql(source=source_db_info, target=target_db_info)
