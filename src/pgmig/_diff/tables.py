from collections.abc import Iterator

from pgmig._diff._core import Options, Phase, Statement, _diff_comments, _iter_table_pairs
from pgmig._models import Column, DbInfo, Table
from pgmig._sql import comment_on, ident, qualified


def _column_def(column: Column) -> str:
    """
    Render a column for CREATE TABLE / ADD COLUMN, with NOT NULL and DEFAULT inline.
    """
    # A serial column expands to its pseudo-type; the integer type, nextval()
    # default and NOT NULL are all implied and must not be emitted alongside it.
    if column.serial_type is not None:
        return f"{ident(column.name)} {column.serial_type}"

    # An identity column has no GENERATED ... AS IDENTITY clause rendered here, so
    # emitting it would create a plain column and silently drop the identity. Refuse
    # loudly rather than produce a migration that never converges.
    if column.identity != "":
        raise NotImplementedError(f"Identity column is not supported: {ident(column.name)}")

    parts = [f"{ident(column.name)} {column.type}"]
    if column.default is not None:
        parts.append(f"DEFAULT {column.default}")
    if column.not_null:
        parts.append("NOT NULL")
    return " ".join(parts)


def _create_table(schema_name: str, table: Table) -> list[str]:
    """
    Render the CREATE TABLE statement for a target-only table (columns inline).
    """
    columns = ", ".join(_column_def(column) for column in table.columns)
    return [f"CREATE TABLE {qualified(schema_name, table.name)} ({columns});"]


def _alter_columns(
    *,
    schema_name: str,
    table_name: str,
    src_table: Table,
    dst_table: Table,
    pk_columns: set[str],
    src_pk_columns: set[str],
) -> tuple[list[str], list[str]]:
    """
    Sync the columns of a table present on both sides: add/drop by name, and for a
    shared column sync DEFAULT then NOT NULL. A type or identity change is unsupported
    and raises rather than emitting a silently-empty (falsely converged) migration.

    Returns (statements, deferred_drop_not_null). The first run in the TABLE phase; the
    second must run after the CONSTRAINT phase (see below).

    A column covered by a target primary key (`pk_columns`) is made NOT NULL by the
    ADD PRIMARY KEY, so its standalone SET NOT NULL is skipped. The mirror case: a column
    covered by the source primary key (`src_pk_columns`) that becomes nullable -- its
    covering PK is dropped this run (a target PK would keep it NOT NULL), and Postgres
    refuses DROP NOT NULL while the column is still in a primary key. That DROP NOT NULL
    is deferred so it can be phased after the CONSTRAINT-phase DROP CONSTRAINT.
    """
    statements: list[str] = []
    deferred_drop_not_null: list[str] = []
    src_columns = {column.name: column for column in src_table.columns}
    dst_columns = {column.name: column for column in dst_table.columns}

    for column_name in sorted(src_columns.keys() | dst_columns.keys()):
        if column_name not in src_columns:
            column = dst_columns[column_name]
            statements.append(f"ALTER TABLE {qualified(schema_name, table_name)} ADD COLUMN {_column_def(column)};")
        elif column_name not in dst_columns:
            statements.append(f"ALTER TABLE {qualified(schema_name, table_name)} DROP COLUMN {ident(column_name)};")
        else:
            src_column = src_columns[column_name]
            dst_column = dst_columns[column_name]
            # Type and identity changes are not yet modelled. Emitting nothing would be
            # indistinguishable from "in sync", so fail loudly instead of lying.
            if src_column.type != dst_column.type:
                raise NotImplementedError(
                    f"Column type change is not supported: "
                    f"{qualified(schema_name, table_name)}.{ident(column_name)} "
                    f"{src_column.type} -> {dst_column.type}"
                )
            if src_column.identity != dst_column.identity:
                raise NotImplementedError(
                    f"Column identity change is not supported: "
                    f"{qualified(schema_name, table_name)}.{ident(column_name)}"
                )
            # A serial change keeps the integer type, so the type guard above does not
            # fire. Its owned sequence is excluded from introspection, so emitting the
            # SET DEFAULT nextval('..._seq') would reference a sequence that is never
            # created (apply fails "relation does not exist"). Raise until real support
            # (create sequence + OWNED BY + default) lands.
            if src_column.serial_type != dst_column.serial_type:
                raise NotImplementedError(
                    f"Column serial change is not supported: "
                    f"{qualified(schema_name, table_name)}.{ident(column_name)} "
                    f"{src_column.serial_type} -> {dst_column.serial_type}"
                )
            prefix = f"ALTER TABLE {qualified(schema_name, table_name)} ALTER COLUMN {ident(column_name)}"
            if src_column.default != dst_column.default:
                if dst_column.default is None:
                    statements.append(f"{prefix} DROP DEFAULT;")
                else:
                    statements.append(f"{prefix} SET DEFAULT {dst_column.default};")
            if src_column.not_null != dst_column.not_null:
                if dst_column.not_null:
                    # Skip if a target primary key already covers this column.
                    if column_name not in pk_columns:
                        statements.append(f"{prefix} SET NOT NULL;")
                elif column_name in src_pk_columns:
                    # Covering source PK drops this run; defer past the CONSTRAINT phase.
                    deferred_drop_not_null.append(f"{prefix} DROP NOT NULL;")
                else:
                    statements.append(f"{prefix} DROP NOT NULL;")
    return statements, deferred_drop_not_null


def _table_comment_statements(schema_name: str, src_table: Table | None, dst_table: Table) -> list[str]:
    """
    Emit COMMENT ON TABLE when the comment differs (absent source table = no comment).
    """
    src_comment = src_table.comment if src_table else None
    dst_comment = dst_table.comment
    if src_comment == dst_comment:
        return []
    return [comment_on("TABLE", qualified(schema_name, dst_table.name), dst_comment)]


def _column_comment_statements(schema_name: str, src_table: Table | None, dst_table: Table) -> list[str]:
    """
    Emit COMMENT ON COLUMN for every target column whose comment differs from the
    source (absent source column = no comment). A separate statement; not inline.
    """
    src_columns = {column.name: column for column in src_table.columns} if src_table else {}
    dst_columns = {column.name: column for column in dst_table.columns}

    return _diff_comments(
        src_columns,
        dst_columns,
        render=lambda name, column: comment_on("COLUMN", qualified(schema_name, dst_table.name, name), column.comment),
    )


def generate(*, source: DbInfo, target: DbInfo, options: Options) -> Iterator[Statement]:
    """
    Generate the migration SQL of tables: drop, create, or alter columns, followed by
    table and column comment sync.
    """
    for schema_name, table_name, src_table, dst_table in _iter_table_pairs(source, target):
        # Present in source only: drop it (attached objects are dropped with it).
        if dst_table is None:
            yield Statement(Phase.TABLE, f"DROP TABLE {qualified(schema_name, table_name)};")
            continue

        deferred_drop_not_null: list[str] = []
        if src_table is None:
            rendered = _create_table(schema_name, dst_table)
        else:
            rendered, deferred_drop_not_null = _alter_columns(
                schema_name=schema_name,
                table_name=table_name,
                src_table=src_table,
                dst_table=dst_table,
                pk_columns=dst_table.get_primary_key_columns(),
                src_pk_columns=src_table.get_primary_key_columns(),
            )
        rendered += _table_comment_statements(schema_name, src_table, dst_table)
        rendered += _column_comment_statements(schema_name, src_table, dst_table)

        for sql in rendered:
            yield Statement(Phase.TABLE, sql)
        # DROP NOT NULL for a column whose covering primary key drops this run must run
        # after the CONSTRAINT-phase DROP CONSTRAINT.
        for sql in deferred_drop_not_null:
            yield Statement(Phase.COLUMN_DROP_NOT_NULL, sql)
