import psycopg

from pgmig._models import Column, DbInfo, Extension, Schema, Table


def build_db_info(dsn: str) -> DbInfo:
    """
    Build the full structure of the given database.
    """
    schema_by_name: dict[str, Schema] = {}
    extension_by_name = {}

    # Construct database attributes.
    with psycopg.connect(dsn, options="-c default_transaction_read_only=on") as conn:
        # Schemas (user namespaces, excluding system and extension-owned ones).
        rows = conn.execute(
            """
            SELECT
                n.nspname
            FROM
                pg_namespace n
            WHERE
                n.nspname NOT LIKE 'pg_%'
                AND n.nspname <> 'information_schema'
                AND NOT EXISTS (
                    SELECT
                        1
                    FROM
                        pg_depend d
                    WHERE
                        d.objid = n.oid
                        AND d.deptype = 'e')
            """
        ).fetchall()
        for (schema_name,) in rows:
            schema_by_name[schema_name] = Schema(name=schema_name, table_by_name={})

        # Tables (and their columns, ordered by name).
        rows = conn.execute(
            """
            SELECT
                n.nspname,
                c.relname,
                a.attname,
                format_type(a.atttypid, a.atttypmod),
                obj_description(c.oid, 'pg_class')
            FROM
                pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_attribute a ON a.attrelid = c.oid
            WHERE
                c.relkind = 'r'
                AND n.nspname NOT LIKE 'pg_%'
                AND n.nspname <> 'information_schema'
                AND NOT EXISTS (
                    SELECT 1 FROM pg_depend d WHERE d.objid = n.oid AND d.deptype = 'e'
                )
                AND a.attnum > 0
                AND NOT a.attisdropped
            ORDER BY
                n.nspname,
                c.relname,
                a.attname
            """
        ).fetchall()
        for schema_name, table_name, column_name, column_type, table_comment in rows:
            if table_name not in schema_by_name[schema_name].table_by_name:
                schema_by_name[schema_name].table_by_name[table_name] = Table(
                    name=table_name,
                    columns=[],
                    comment=table_comment,
                )
            schema_by_name[schema_name].table_by_name[table_name].columns.append(
                Column(name=column_name, type=column_type)
            )

        # Extensions (database-level).
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

    # Build and return the database info.
    return DbInfo(
        extension_by_name=extension_by_name,
        schema_by_name=schema_by_name,
    )
