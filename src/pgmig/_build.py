import psycopg

from pgmig._models import Column, Extension, Schema, Table


def build_schema(dsn: str) -> Schema:
    """
    Build the database schema of the given database.
    """
    extension_by_name = {}
    columns_by_table: dict[tuple[str, str], list[Column]] = {}

    # Construct schema attributes.
    with psycopg.connect(dsn, options="-c default_transaction_read_only=on") as conn:
        # Extensions.
        rows = conn.execute(
            """
            SELECT
                e.extname,
                e.extversion,
                n.nspname
            FROM
                pg_extension e
                JOIN pg_namespace n ON n.oid = e.extnamespace
            """
        ).fetchall()
        for name, version, schema in rows:
            extension_by_name[name] = Extension(name=name, version=version, schema=schema)

        # Tables (and their columns, ordered by position).
        rows = conn.execute(
            """
            SELECT
                n.nspname,
                c.relname,
                a.attname,
                format_type(a.atttypid, a.atttypmod)
            FROM
                pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_attribute a ON a.attrelid = c.oid
            WHERE
                c.relkind = 'r'
                AND n.nspname NOT IN ('pg_catalog', 'information_schema')
                AND a.attnum > 0
                AND NOT a.attisdropped
            ORDER BY
                n.nspname,
                c.relname,
                a.attnum
            """
        ).fetchall()
        for schema, table_name, column_name, column_type in rows:
            columns_by_table.setdefault((schema, table_name), []).append(Column(name=column_name, type=column_type))

    table_by_key = {
        key: Table(schema=key[0], name=key[1], columns=tuple(columns)) for key, columns in columns_by_table.items()
    }

    # Build and return the schema.
    return Schema(
        extension_by_name=extension_by_name,
        table_by_key=table_by_key,
    )
