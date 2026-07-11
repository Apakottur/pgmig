from dataclasses import dataclass

import psycopg


@dataclass
class Schema:
    """
    Database schema.
    """


def _get_db_schema(dsn: str) -> Schema:
    """
    Get the database schema from the given DSN.
    """
    # Start with an empty schema.
    s = Schema()

    # Construct schema attributes.
    with psycopg.connect(dsn) as conn:
        conn.execute("SELECT 1")

    # Return the schema.
    return s


def _get_migration_sql(*, source: Schema, target: Schema) -> str:
    """
    Get the migration SQL between the given source and target schemas.
    """
    if source == target:
        return ""
    else:
        raise NotImplementedError


def generate(*, source: str, target: str) -> str:
    """
    Generate the migration SQL between the given source and target databases.
    """
    # Get source schema.
    source_schema = _get_db_schema(source)

    # Get target schema.
    target_schema = _get_db_schema(target)

    # Get the migration SQL.
    return _get_migration_sql(source=source_schema, target=target_schema)
