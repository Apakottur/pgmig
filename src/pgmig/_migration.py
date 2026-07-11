from psycopg import sql

from pgmig._models import DbInfo, Table


def _generate_schemas(*, source: DbInfo, target: DbInfo) -> tuple[list[str], list[str]]:
    """
    Generate the migration SQL of schemas.

    Returns (creates, drops) separately so the caller can order creates before,
    and drops after, the objects that live inside the schemas.
    """
    creates: list[str] = []
    drops: list[str] = []

    for name in sorted(source.schema_by_name.keys() | target.schema_by_name.keys()):
        # Present in target only: create it.
        if name not in source.schema_by_name:
            creates.append(sql.SQL("CREATE SCHEMA {name};").format(name=sql.Identifier(name)).as_string())
        # Present in source only: drop it.
        elif name not in target.schema_by_name:
            drops.append(sql.SQL("DROP SCHEMA {name};").format(name=sql.Identifier(name)).as_string())

    return creates, drops


def _generate_extensions(*, source: DbInfo, target: DbInfo) -> list[str]:
    """
    Generate the migration SQL of extensions.
    """
    statements: list[str] = []

    for name in sorted(source.extension_by_name.keys() | target.extension_by_name.keys()):
        # Present in target only: create it.
        if name not in source.extension_by_name:
            dst_ext = target.extension_by_name[name]
            statements.append(
                sql.SQL("CREATE EXTENSION {name} VERSION {version} SCHEMA {schema};")
                .format(
                    name=sql.Identifier(dst_ext.name),
                    version=sql.Literal(dst_ext.version),
                    schema=sql.Identifier(dst_ext.schema),
                )
                .as_string()
            )
        # Present in source only: drop it.
        elif name not in target.extension_by_name:
            src_ext = source.extension_by_name[name]
            statements.append(sql.SQL("DROP EXTENSION {name};").format(name=sql.Identifier(src_ext.name)).as_string())

        # Present in both: alter version and/or schema if they differ.
        else:
            src_ext = source.extension_by_name[name]
            dst_ext = target.extension_by_name[name]
            if src_ext.version != dst_ext.version:
                statements.append(
                    sql.SQL("ALTER EXTENSION {name} UPDATE TO {version};")
                    .format(
                        name=sql.Identifier(dst_ext.name),
                        version=sql.Literal(dst_ext.version),
                    )
                    .as_string()
                )
            if src_ext.schema != dst_ext.schema:
                statements.append(
                    sql.SQL("ALTER EXTENSION {name} SET SCHEMA {schema};")
                    .format(
                        name=sql.Identifier(dst_ext.name),
                        schema=sql.Identifier(dst_ext.schema),
                    )
                    .as_string()
                )
    return statements


def _create_table_sql(*, schema_name: str, table: Table) -> str:
    """
    Generate the CREATE TABLE SQL for a single table.
    """
    columns = sql.SQL(", ").join(
        sql.SQL("{name} {type}").format(
            name=sql.Identifier(column.name),
            # The type is canonical SQL produced by format_type, safe to inline.
            type=sql.SQL(column.type),  # ty: ignore[invalid-argument-type]
        )
        for column in table.columns
    )
    return (
        sql.SQL("CREATE TABLE {name} ({columns});")
        .format(
            name=sql.Identifier(schema_name, table.name),
            columns=columns,
        )
        .as_string()
    )


def _generate_tables(*, source: DbInfo, target: DbInfo) -> list[str]:
    """
    Generate the migration SQL of tables.
    """
    statements: list[str] = []

    for schema_name in sorted(source.schema_by_name.keys() | target.schema_by_name.keys()):
        src_schema = source.schema_by_name.get(schema_name)
        dst_schema = target.schema_by_name.get(schema_name)
        src_tables = src_schema.table_by_name if src_schema else {}
        dst_tables = dst_schema.table_by_name if dst_schema else {}

        for table_name in sorted(src_tables.keys() | dst_tables.keys()):
            # Present in target only: create it.
            if table_name not in src_tables:
                statements.append(_create_table_sql(schema_name=schema_name, table=dst_tables[table_name]))
            # Present in source only: drop it.
            elif table_name not in dst_tables:
                statements.append(
                    sql.SQL("DROP TABLE {name};").format(name=sql.Identifier(schema_name, table_name)).as_string()
                )

    return statements


def generate_migration_sql(*, source: DbInfo, target: DbInfo) -> str:
    """
    Get the migration SQL between the given source and target databases.
    """
    statements: list[str] = []

    # Schemas must be created before the objects inside them, and dropped after.
    schema_creates, schema_drops = _generate_schemas(source=source, target=target)

    statements.extend(schema_creates)
    statements.extend(_generate_extensions(source=source, target=target))
    statements.extend(_generate_tables(source=source, target=target))
    statements.extend(schema_drops)

    # All statements.
    return "\n".join(statements)
