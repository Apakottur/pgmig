from dataclasses import dataclass

import psycopg


@dataclass
class Schema:
    """
    Database schema.
    """


def _get_db_schema(dsn: str) -> Schema:
    # Start with an empty schema.
    s = Schema()

    # Get the schema from the database.
    with psycopg.connect(dsn) as conn:
        conn.execute("SELECT 1")

    # Return the schema.
    return s


def _get_migration_sql(*, source: Schema, target: Schema) -> str:
    if source == target:
        return ""
    else:
        raise NotImplementedError


def generate(*, source: str, target: str) -> str:
    # Get source schema.
    source_schema = _get_db_schema(source)

    # Get target schema.
    target_schema = _get_db_schema(target)

    # Get the migration SQL.
    return _get_migration_sql(source=source_schema, target=target_schema)
