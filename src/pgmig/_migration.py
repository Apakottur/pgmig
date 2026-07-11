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
            # Present in source only: drop it (attached objects are dropped with it).
            if table_name not in dst_tables:
                drop_table_sql = f'DROP TABLE "{schema_name}"."{table_name}";'
                statements.append(drop_table_sql)
                continue

            if table_name in src_tables:
                # Table exists in source: get details.
                src_comment = src_tables[table_name].comment
            else:
                # Present in target only: create it.
                columns = ", ".join(f'"{column.name}" {column.type}' for column in dst_tables[table_name].columns)
                create_table_sql = f'CREATE TABLE "{schema_name}"."{table_name}" ({columns});'
                statements.append(create_table_sql)

                # Default table attributes are
                src_comment = None

            # Apply changes to an existing (or newly created) table.

            # Sync comment.
            dst_comment = dst_tables[table_name].comment
            if src_comment != dst_comment:
                if dst_comment is None:
                    statements.append(f'COMMENT ON TABLE "{schema_name}"."{table_name}" IS NULL;')
                else:
                    escaped = dst_comment.replace("'", "''")
                    statements.append(f'COMMENT ON TABLE "{schema_name}"."{table_name}" IS \'{escaped}\';')

    return statements


def _generate_indexes(*, source: DbInfo, target: DbInfo) -> list[str]:
    """
    Generate the migration SQL of standalone indexes (create, drop, rename).
    """
    statements: list[str] = []

    for schema_name in sorted(source.schema_by_name.keys() | target.schema_by_name.keys()):
        src_schema = source.schema_by_name.get(schema_name)
        dst_schema = target.schema_by_name.get(schema_name)
        src_tables = src_schema.table_by_name if src_schema else {}
        dst_tables = dst_schema.table_by_name if dst_schema else {}

        for table_name in sorted(src_tables.keys() | dst_tables.keys()):
            # Table dropped: its indexes are dropped with it.
            if table_name not in dst_tables:
                continue

            src_indexes = dict(src_tables[table_name].index_by_name) if table_name in src_tables else {}
            dst_indexes = dict(dst_tables[table_name].index_by_name)

            # Exact matches (same name and definition) are no-ops.
            for name in sorted(src_indexes.keys() & dst_indexes.keys()):
                if src_indexes[name].definition == dst_indexes[name].definition:
                    del src_indexes[name]
                    del dst_indexes[name]

            # Renames: remaining indexes that share a canonical (name-independent) key.
            src_by_canonical: dict[str, list[str]] = {}
            for name, index in src_indexes.items():
                src_by_canonical.setdefault(index.canonical, []).append(name)
            dst_by_canonical: dict[str, list[str]] = {}
            for name, index in dst_indexes.items():
                dst_by_canonical.setdefault(index.canonical, []).append(name)

            rename_pairs: list[tuple[str, str]] = []
            for canonical in sorted(src_by_canonical.keys() & dst_by_canonical.keys()):
                src_names = sorted(src_by_canonical[canonical])
                dst_names = sorted(dst_by_canonical[canonical])
                # A shared canonical key with an identical name implies an identical
                # definition, which was already removed as an exact match above, so
                # every pair here is a genuine rename. Counts may differ, so pair up
                # to the shorter list.
                for old_name, new_name in zip(src_names, dst_names, strict=False):
                    rename_pairs.append((old_name, new_name))
                    del src_indexes[old_name]
                    del dst_indexes[new_name]

            # Emit drops first (frees names), then renames, then creates.
            statements.extend(f'DROP INDEX "{schema_name}"."{name}";' for name in sorted(src_indexes.keys()))
            statements.extend(
                f'ALTER INDEX "{schema_name}"."{old_name}" RENAME TO "{new_name}";'
                for old_name, new_name in rename_pairs
            )
            statements.extend(f"{dst_indexes[name].definition};" for name in sorted(dst_indexes.keys()))

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
    index_statements = _generate_indexes(source=source, target=target)

    # Add statements in the correct order.
    statements.extend(schema_creates)
    statements.extend(extension_statements)
    statements.extend(table_statements)
    statements.extend(index_statements)
    statements.extend(schema_drops)

    # Join all statements into a single string.
    return "\n".join(statements)
