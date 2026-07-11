import psycopg

from pgmig._models import Column, Constraint, DbInfo, Extension, Index, Schema, Table


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
                a.attnotnull,
                pg_get_expr(ad.adbin, ad.adrelid),
                col_description(a.attrelid, a.attnum),
                obj_description(c.oid, 'pg_class')
            FROM
                pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_attribute a ON a.attrelid = c.oid
                LEFT JOIN pg_attrdef ad ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum
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
        for (
            schema_name,
            table_name,
            column_name,
            column_type,
            column_not_null,
            column_default,
            column_comment,
            table_comment,
        ) in rows:
            if table_name not in schema_by_name[schema_name].table_by_name:
                schema_by_name[schema_name].table_by_name[table_name] = Table(
                    name=table_name,
                    columns=[],
                    comment=table_comment,
                    index_by_name={},
                    constraint_by_name={},
                )
            schema_by_name[schema_name].table_by_name[table_name].columns.append(
                Column(
                    name=column_name,
                    type=column_type,
                    not_null=column_not_null,
                    default=column_default,
                    comment=column_comment,
                )
            )

        # Indexes (standalone only; constraint-backed indexes are excluded).
        rows = conn.execute(
            """
            SELECT
                n.nspname,
                c.relname,
                ic.relname,
                pg_get_indexdef(i.indexrelid),
                replace(
                    pg_get_indexdef(i.indexrelid),
                    'INDEX ' || quote_ident(ic.relname) || ' ON ',
                    'INDEX ON ')
            FROM
                pg_index i
                JOIN pg_class ic ON ic.oid = i.indexrelid
                JOIN pg_class c ON c.oid = i.indrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
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
                AND NOT i.indisprimary
                AND NOT EXISTS (
                    SELECT
                        1
                    FROM
                        pg_depend d
                    WHERE
                        d.classid = 'pg_class'::regclass
                        AND d.objid = i.indexrelid
                        AND d.refclassid = 'pg_constraint'::regclass
                        AND d.deptype = 'i')
            """
        ).fetchall()
        for schema_name, table_name, index_name, index_def, index_canonical in rows:
            schema_by_name[schema_name].table_by_name[table_name].index_by_name[index_name] = Index(
                name=index_name,
                definition=index_def,
                canonical=index_canonical,
            )

        # Constraints (primary key and unique only).
        rows = conn.execute(
            """
            SELECT
                n.nspname,
                c.relname,
                con.conname,
                pg_get_constraintdef(con.oid),
                con.contype = 'p',
                (SELECT
                    array_agg(a.attname ORDER BY k.ord)
                 FROM
                    unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord)
                    JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum)
            FROM
                pg_constraint con
                JOIN pg_class c ON c.oid = con.conrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE
                con.contype IN ('p', 'u')
                AND n.nspname NOT LIKE 'pg_%'
                AND n.nspname <> 'information_schema'
                AND NOT EXISTS (
                    SELECT 1 FROM pg_depend d WHERE d.objid = n.oid AND d.deptype = 'e'
                )
            """
        ).fetchall()
        for schema_name, table_name, con_name, con_def, con_is_pk, con_columns in rows:
            schema_by_name[schema_name].table_by_name[table_name].constraint_by_name[con_name] = Constraint(
                name=con_name,
                definition=con_def,
                is_primary_key=con_is_pk,
                columns=con_columns,
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
