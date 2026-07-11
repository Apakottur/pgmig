from pgmig._models import Column, DbInfo


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


def _column_def(column: Column) -> str:
    """
    Render a column for CREATE TABLE / ADD COLUMN, with NOT NULL and DEFAULT inline.
    """
    parts = [f'"{column.name}" {column.type}']
    if column.default is not None:
        parts.append(f"DEFAULT {column.default}")
    if column.not_null:
        parts.append("NOT NULL")
    return " ".join(parts)


def _column_comment_statements(
    *,
    schema_name: str,
    table_name: str,
    src_columns: dict[str, Column],
    dst_columns: dict[str, Column],
) -> list[str]:
    """
    Generate COMMENT ON COLUMN statements for every target column whose comment
    differs from the source (absent source column is treated as no comment).
    """
    statements: list[str] = []
    for column_name in sorted(dst_columns.keys()):
        src_comment = src_columns[column_name].comment if column_name in src_columns else None
        dst_comment = dst_columns[column_name].comment
        if src_comment != dst_comment:
            if dst_comment is None:
                target = "NULL"
            else:
                escaped = dst_comment.replace("'", "''")
                target = f"'{escaped}'"
            statements.append(f'COMMENT ON COLUMN "{schema_name}"."{table_name}"."{column_name}" IS {target};')
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

            # Columns covered by a target primary key are made NOT NULL by the
            # ADD PRIMARY KEY, so their standalone SET NOT NULL is redundant.
            dst_pk_columns = dst_tables[table_name].get_primary_key_columns()

            if table_name in src_tables:
                # Table exists in source: get details.
                src_comment = src_tables[table_name].comment
                src_columns = {column.name: column for column in src_tables[table_name].columns}

                # Sync columns (add/drop by name; type changes are out of scope).
                dst_columns = {column.name: column for column in dst_tables[table_name].columns}
                for column_name in sorted(src_columns.keys() | dst_columns.keys()):
                    if column_name not in src_columns:
                        column = dst_columns[column_name]
                        statements.append(
                            f'ALTER TABLE "{schema_name}"."{table_name}" ADD COLUMN {_column_def(column)};'
                        )
                    elif column_name not in dst_columns:
                        statements.append(f'ALTER TABLE "{schema_name}"."{table_name}" DROP COLUMN "{column_name}";')
                    else:
                        # Column on both sides: sync DEFAULT then NOT NULL (type changes are out of scope).
                        src_column = src_columns[column_name]
                        dst_column = dst_columns[column_name]
                        prefix = f'ALTER TABLE "{schema_name}"."{table_name}" ALTER COLUMN "{column_name}"'
                        if src_column.default != dst_column.default:
                            if dst_column.default is None:
                                statements.append(f"{prefix} DROP DEFAULT;")
                            else:
                                statements.append(f"{prefix} SET DEFAULT {dst_column.default};")
                        if src_column.not_null != dst_column.not_null:
                            if dst_column.not_null:
                                # Skip if a target primary key already covers this column.
                                if column_name not in dst_pk_columns:
                                    statements.append(f"{prefix} SET NOT NULL;")
                            else:
                                statements.append(f"{prefix} DROP NOT NULL;")
            else:
                # Present in target only: default details.
                src_comment = None
                src_columns = {}

                # Create the table.
                dst_columns = {column.name: column for column in dst_tables[table_name].columns}
                columns = ", ".join(_column_def(column) for column in dst_tables[table_name].columns)
                create_table_sql = f'CREATE TABLE "{schema_name}"."{table_name}" ({columns});'
                statements.append(create_table_sql)

            # Sync table comment.
            dst_comment = dst_tables[table_name].comment
            if src_comment != dst_comment:
                if dst_comment is None:
                    statements.append(f'COMMENT ON TABLE "{schema_name}"."{table_name}" IS NULL;')
                else:
                    escaped = dst_comment.replace("'", "''")
                    statements.append(f'COMMENT ON TABLE "{schema_name}"."{table_name}" IS \'{escaped}\';')

            # Sync column comments (a separate statement; cannot be inline).
            statements.extend(
                _column_comment_statements(
                    schema_name=schema_name,
                    table_name=table_name,
                    src_columns=src_columns,
                    dst_columns=dst_columns,
                )
            )

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


def _generate_constraints(*, source: DbInfo, target: DbInfo) -> list[str]:
    """
    Generate the migration SQL of primary key, unique, and check constraints (add, drop, rename).
    """
    statements: list[str] = []

    for schema_name in sorted(source.schema_by_name.keys() | target.schema_by_name.keys()):
        src_schema = source.schema_by_name.get(schema_name)
        dst_schema = target.schema_by_name.get(schema_name)
        src_tables = src_schema.table_by_name if src_schema else {}
        dst_tables = dst_schema.table_by_name if dst_schema else {}

        for table_name in sorted(src_tables.keys() | dst_tables.keys()):
            # Table dropped: its constraints are dropped with it.
            if table_name not in dst_tables:
                continue

            src_constraints = dict(src_tables[table_name].constraint_by_name) if table_name in src_tables else {}
            dst_constraints = dict(dst_tables[table_name].constraint_by_name)

            # Exact matches (same name and definition) are no-ops.
            for name in sorted(src_constraints.keys() & dst_constraints.keys()):
                if src_constraints[name].definition == dst_constraints[name].definition:
                    del src_constraints[name]
                    del dst_constraints[name]

            # Renames: remaining constraints that share a definition (name-independent).
            src_by_def: dict[str, list[str]] = {}
            for name, constraint in src_constraints.items():
                src_by_def.setdefault(constraint.definition, []).append(name)
            dst_by_def: dict[str, list[str]] = {}
            for name, constraint in dst_constraints.items():
                dst_by_def.setdefault(constraint.definition, []).append(name)

            rename_pairs: list[tuple[str, str]] = []
            for definition in sorted(src_by_def.keys() & dst_by_def.keys()):
                src_names = sorted(src_by_def[definition])
                dst_names = sorted(dst_by_def[definition])
                # Same definition with an identical name was already removed as an exact
                # match, so every pair here is a genuine rename. Counts may differ, so
                # pair up to the shorter list.
                for old_name, new_name in zip(src_names, dst_names, strict=False):
                    rename_pairs.append((old_name, new_name))
                    del src_constraints[old_name]
                    del dst_constraints[new_name]

            # Emit drops first (frees names), then renames, then adds.
            statements.extend(
                f'ALTER TABLE "{schema_name}"."{table_name}" DROP CONSTRAINT "{name}";'
                for name in sorted(src_constraints.keys())
            )
            statements.extend(
                f'ALTER TABLE "{schema_name}"."{table_name}" RENAME CONSTRAINT "{old_name}" TO "{new_name}";'
                for old_name, new_name in rename_pairs
            )
            statements.extend(
                f'ALTER TABLE "{schema_name}"."{table_name}" ADD CONSTRAINT "{name}" {dst_constraints[name].definition};'
                for name in sorted(dst_constraints.keys())
            )

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
    constraint_statements = _generate_constraints(source=source, target=target)

    # Add statements in the correct order.
    statements.extend(schema_creates)
    statements.extend(extension_statements)
    statements.extend(table_statements)
    statements.extend(index_statements)
    statements.extend(constraint_statements)
    statements.extend(schema_drops)

    # Join all statements into a single string.
    return "\n".join(statements)
