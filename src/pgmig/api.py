from pgmig._build import build_schema
from pgmig._migration import generate_schema_migration_sql


def generate(*, source: str, target: str) -> str:
    """
    Generate the migration SQL between the given source and target databases.
    """
    # Build source schema.
    source_schema = build_schema(source)

    # Build target schema.
    target_schema = build_schema(target)

    # Generate migration SQL.
    return generate_schema_migration_sql(source=source_schema, target=target_schema)
