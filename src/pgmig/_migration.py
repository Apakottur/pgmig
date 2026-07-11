from pgmig._models import DbInfo


def _generate_schemas(*, source: DbInfo, target: DbInfo) -> tuple[list[str], list[str]]:
    """
    Generate the migration SQL of schemas.

    Returns:
        A 2-tuple of schema lists: (creates, drops).
    """
    creates: list[str] = []
    drops: list[str] = []

    for name in sorted(source.schema_by_name.keys() | target.schema_by_name.keys()):
        # Present in target only: create it.
        if name not in source.schema_by_name:
            creates.append(f'CREATE SCHEMA "{name}";')
        # Present in source only: drop it.
        elif name not in target.schema_by_name:
            drops.append(f'DROP SCHEMA "{name}";')

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
                f'CREATE EXTENSION "{dst_ext.name}" VERSION \'{dst_ext.version}\' SCHEMA "{dst_ext.schema}";'
            )
        # Present in source only: drop it.
        elif name not in target.extension_by_name:
            src_ext = source.extension_by_name[name]
            statements.append(f'DROP EXTENSION "{src_ext.name}";')

        # Present in both: alter version and/or schema if they differ.
        else:
            src_ext = source.extension_by_name[name]
            dst_ext = target.extension_by_name[name]
            if src_ext.version != dst_ext.version:
                statements.append(f"ALTER EXTENSION \"{dst_ext.name}\" UPDATE TO '{dst_ext.version}';")
            if src_ext.schema != dst_ext.schema:
                statements.append(f'ALTER EXTENSION "{dst_ext.name}" SET SCHEMA "{dst_ext.schema}";')
    return statements


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
                columns = ", ".join(f'"{column.name}" {column.type}' for column in dst_tables[table_name].columns)
                create_table_sql = f'CREATE TABLE "{schema_name}"."{table_name}" ({columns});'
                statements.append(create_table_sql)
            # Present in source only: drop it.
            elif table_name not in dst_tables:
                drop_table_sql = f'DROP TABLE "{schema_name}"."{table_name}";'
                statements.append(drop_table_sql)

    return statements


def generate_migration_sql(*, source: DbInfo, target: DbInfo) -> str:
    """
    Get the migration SQL between the given source and target databases.
    """
    statements: list[str] = []

    # Generate all statements.
    schema_creates, schema_drops = _generate_schemas(source=source, target=target)
    extension_statements = _generate_extensions(source=source, target=target)
    table_statements = _generate_tables(source=source, target=target)

    # Add statements in the correct order.
    statements.extend(schema_creates)
    statements.extend(extension_statements)
    statements.extend(table_statements)
    statements.extend(schema_drops)

    # Join all statements into a single string.
    return "\n".join(statements)
