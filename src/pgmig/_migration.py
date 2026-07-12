from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import Enum, auto
from typing import TypeVar

from pgmig._models import Column, Constraint, DbInfo, Index, Schema, Sequence, Table
from pgmig._sql import ident, literal, qualified

_Renamable = TypeVar("_Renamable")


class Phase(Enum):
    """
    Global ordering bucket for a migration statement. Members are declared in
    execution order (priority); statements are grouped by phase and emitted by
    iterating the enum, so a statement's position is decided by its dependency
    phase, not by generator call order.
    """

    FOREIGN_KEY_DROP = auto()  # Before a referenced table / key is dropped.
    FUNCTION_DROP = auto()  # Before tables a routine body may depend on.
    SCHEMA_CREATE = auto()
    EXTENSION = auto()
    SEQUENCE_CREATE = auto()  # Before tables (a column default may reference a sequence).
    TABLE = auto()
    INDEX = auto()
    CONSTRAINT = auto()
    FUNCTION_CREATE = auto()  # After tables so routine bodies can reference them.
    FOREIGN_KEY_ADD = auto()  # After referenced tables and their keys exist.
    SEQUENCE_DROP = auto()  # After tables that referenced the sequence are gone.
    SCHEMA_DROP = auto()


@dataclass(frozen=True)
class Statement:
    """
    A migration SQL statement tagged with the phase that fixes its global position.
    """

    phase: Phase
    sql: str


def _iter_schema_pairs(source: DbInfo, target: DbInfo) -> Iterator[tuple[str, Schema | None, Schema | None]]:
    """
    Yield (schema_name, source_schema, target_schema) for every schema across both
    databases, sorted by name. Either schema is None when absent on that side.
    """
    for schema_name in sorted(source.schema_by_name.keys() | target.schema_by_name.keys()):
        yield schema_name, source.schema_by_name.get(schema_name), target.schema_by_name.get(schema_name)


def _iter_table_pairs(source: DbInfo, target: DbInfo) -> Iterator[tuple[str, str, Table | None, Table | None]]:
    """
    Yield (schema_name, table_name, source_table, target_table) for every table across
    both databases, sorted by schema then table. Either table is None when absent on
    that side.
    """
    for schema_name, src_schema, dst_schema in _iter_schema_pairs(source, target):
        src_tables = src_schema.table_by_name if src_schema else {}
        dst_tables = dst_schema.table_by_name if dst_schema else {}
        for table_name in sorted(src_tables.keys() | dst_tables.keys()):
            yield schema_name, table_name, src_tables.get(table_name), dst_tables.get(table_name)


def _generate_schemas(*, source: DbInfo, target: DbInfo) -> list[Statement]:
    """
    Generate the migration SQL of schemas.
    """
    statements: list[Statement] = []

    for name in sorted(source.schema_by_name.keys() | target.schema_by_name.keys()):
        # Present in target only: create it.
        if name not in source.schema_by_name:
            statements.append(Statement(Phase.SCHEMA_CREATE, f"CREATE SCHEMA {ident(name)};"))
        # Present in source only: drop it.
        elif name not in target.schema_by_name:
            statements.append(Statement(Phase.SCHEMA_DROP, f"DROP SCHEMA {ident(name)};"))

    return statements


def _generate_extensions(*, source: DbInfo, target: DbInfo) -> list[Statement]:
    """
    Generate the migration SQL of extensions.
    """
    statements: list[Statement] = []

    for name in sorted(source.extension_by_name.keys() | target.extension_by_name.keys()):
        # Present in target only: create it.
        if name not in source.extension_by_name:
            dst_ext = target.extension_by_name[name]
            statements.append(
                Statement(
                    Phase.EXTENSION,
                    f"CREATE EXTENSION {ident(dst_ext.name)} VERSION {literal(dst_ext.version)}"
                    f" SCHEMA {ident(dst_ext.schema)};",
                )
            )
        # Present in source only: drop it.
        elif name not in target.extension_by_name:
            src_ext = source.extension_by_name[name]
            statements.append(Statement(Phase.EXTENSION, f"DROP EXTENSION {ident(src_ext.name)};"))

        # Present in both: alter version and/or schema if they differ.
        else:
            src_ext = source.extension_by_name[name]
            dst_ext = target.extension_by_name[name]
            if src_ext.version != dst_ext.version:
                statements.append(
                    Statement(
                        Phase.EXTENSION,
                        f"ALTER EXTENSION {ident(dst_ext.name)} UPDATE TO {literal(dst_ext.version)};",
                    )
                )
            if src_ext.schema != dst_ext.schema:
                statements.append(
                    Statement(
                        Phase.EXTENSION, f"ALTER EXTENSION {ident(dst_ext.name)} SET SCHEMA {ident(dst_ext.schema)};"
                    )
                )
    return statements


def _column_def(column: Column) -> str:
    """
    Render a column for CREATE TABLE / ADD COLUMN, with NOT NULL and DEFAULT inline.
    """
    # A serial column expands to its pseudo-type; the integer type, nextval()
    # default and NOT NULL are all implied and must not be emitted alongside it.
    if column.serial_type is not None:
        return f"{ident(column.name)} {column.serial_type}"

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
    *, schema_name: str, table_name: str, src_table: Table, dst_table: Table, pk_columns: set[str]
) -> list[str]:
    """
    Sync the columns of a table present on both sides: add/drop by name, and for a
    shared column sync DEFAULT then NOT NULL. Type changes are out of scope.

    A column covered by a target primary key (`pk_columns`) is made NOT NULL by the
    ADD PRIMARY KEY, so its standalone SET NOT NULL is skipped. Passing the set in
    keeps that cross-object coordination an explicit seam.
    """
    statements: list[str] = []
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
                else:
                    statements.append(f"{prefix} DROP NOT NULL;")
    return statements


def _table_comment_statements(schema_name: str, src_table: Table | None, dst_table: Table) -> list[str]:
    """
    Emit COMMENT ON TABLE when the comment differs (absent source table = no comment).
    """
    src_comment = src_table.comment if src_table else None
    dst_comment = dst_table.comment
    if src_comment == dst_comment:
        return []
    target = "NULL" if dst_comment is None else literal(dst_comment)
    return [f"COMMENT ON TABLE {qualified(schema_name, dst_table.name)} IS {target};"]


def _column_comment_statements(schema_name: str, src_table: Table | None, dst_table: Table) -> list[str]:
    """
    Emit COMMENT ON COLUMN for every target column whose comment differs from the
    source (absent source column = no comment). A separate statement; not inline.
    """
    src_columns = {column.name: column for column in src_table.columns} if src_table else {}
    dst_columns = {column.name: column for column in dst_table.columns}

    statements: list[str] = []
    for column_name in sorted(dst_columns.keys()):
        src_comment = src_columns[column_name].comment if column_name in src_columns else None
        dst_comment = dst_columns[column_name].comment
        if src_comment != dst_comment:
            target = "NULL" if dst_comment is None else literal(dst_comment)
            statements.append(f"COMMENT ON COLUMN {qualified(schema_name, dst_table.name, column_name)} IS {target};")
    return statements


def _generate_tables(*, source: DbInfo, target: DbInfo) -> list[Statement]:
    """
    Generate the migration SQL of tables: drop, create, or alter columns, followed by
    table and column comment sync.
    """
    statements: list[str] = []

    for schema_name, table_name, src_table, dst_table in _iter_table_pairs(source, target):
        # Present in source only: drop it (attached objects are dropped with it).
        if dst_table is None:
            statements.append(f"DROP TABLE {qualified(schema_name, table_name)};")
            continue

        if src_table is None:
            statements.extend(_create_table(schema_name, dst_table))
        else:
            statements.extend(
                _alter_columns(
                    schema_name=schema_name,
                    table_name=table_name,
                    src_table=src_table,
                    dst_table=dst_table,
                    pk_columns=dst_table.get_primary_key_columns(),
                )
            )

        statements.extend(_table_comment_statements(schema_name, src_table, dst_table))
        statements.extend(_column_comment_statements(schema_name, src_table, dst_table))

    return [Statement(Phase.TABLE, sql) for sql in statements]


def _generate_indexes(*, source: DbInfo, target: DbInfo) -> list[Statement]:
    """
    Generate the migration SQL of standalone indexes (create, drop, rename).
    """
    statements: list[str] = []

    for schema_name, _table_name, src_table, dst_table in _iter_table_pairs(source, target):
        # Table dropped: its indexes are dropped with it.
        if dst_table is None:
            continue

        src_indexes = src_table.index_by_name if src_table else {}
        drops, renames, creates = _diff_indexes(schema_name=schema_name, src=src_indexes, dst=dst_table.index_by_name)
        # Emit drops first (frees names), then renames, then creates.
        statements.extend(drops)
        statements.extend(renames)
        statements.extend(creates)

    return [Statement(Phase.INDEX, sql) for sql in statements]


def _diff_renamable(
    src: dict[str, _Renamable],
    dst: dict[str, _Renamable],
    *,
    key: Callable[[_Renamable], str],
    render_drop: Callable[[str], str],
    render_rename: Callable[[str, str], str],
    render_create: Callable[[str, _Renamable], str],
) -> tuple[list[str], list[str], list[str]]:
    """
    Diff two name->object mappings whose objects carry a name-independent `key`,
    detecting renames (same key, different name).

    Returns:
        A 3-tuple (drops, renames, creates) of rendered SQL statements. A shared
        name is a no-op when the keys match; otherwise objects are dropped,
        renamed (same key across a name change), or created.
    """
    src = dict(src)
    dst = dict(dst)

    # Same name + same key means no change.
    for name in sorted(src.keys() & dst.keys()):
        if key(src[name]) == key(dst[name]):
            del src[name]
            del dst[name]

    # Renames: remaining objects that share a name-independent key.
    src_by_key: dict[str, list[str]] = {}
    for name, item in src.items():
        src_by_key.setdefault(key(item), []).append(name)
    dst_by_key: dict[str, list[str]] = {}
    for name, item in dst.items():
        dst_by_key.setdefault(key(item), []).append(name)

    renames: list[str] = []
    for shared_key in sorted(src_by_key.keys() & dst_by_key.keys()):
        src_names = sorted(src_by_key[shared_key])
        dst_names = sorted(dst_by_key[shared_key])
        # A shared key with an identical name was removed as a no-op above, so every
        # pair here is a genuine rename. Counts may differ, so pair up to the shorter.
        for old_name, new_name in zip(src_names, dst_names, strict=False):
            renames.append(render_rename(old_name, new_name))
            del src[old_name]
            del dst[new_name]

    drops = [render_drop(name) for name in sorted(src.keys())]
    creates = [render_create(name, dst[name]) for name in sorted(dst.keys())]
    return drops, renames, creates


def _diff_indexes(
    *, schema_name: str, src: dict[str, Index], dst: dict[str, Index]
) -> tuple[list[str], list[str], list[str]]:
    """
    Diff one table's standalone indexes into (drops, renames, creates), using each
    index's name-independent canonical form as the rename key.
    """
    return _diff_renamable(
        src,
        dst,
        key=lambda index: index.canonical,
        render_drop=lambda name: f"DROP INDEX {qualified(schema_name, name)};",
        render_rename=lambda old, new: f"ALTER INDEX {qualified(schema_name, old)} RENAME TO {ident(new)};",
        render_create=lambda _name, index: f"{index.definition};",
    )


def _diff_constraints(
    *, schema_name: str, table_name: str, src: dict[str, Constraint], dst: dict[str, Constraint]
) -> tuple[list[str], list[str], list[str]]:
    """
    Diff one table's constraints (of a single kind) into (drops, renames, adds).
    The constraint definition (from pg_get_constraintdef) is already name-independent.
    """
    prefix = f"ALTER TABLE {qualified(schema_name, table_name)}"
    return _diff_renamable(
        src,
        dst,
        key=lambda constraint: constraint.definition,
        render_drop=lambda name: f"{prefix} DROP CONSTRAINT {ident(name)};",
        render_rename=lambda old, new: f"{prefix} RENAME CONSTRAINT {ident(old)} TO {ident(new)};",
        render_create=lambda name, constraint: f"{prefix} ADD CONSTRAINT {ident(name)} {constraint.definition};",
    )


def _generate_constraints(*, source: DbInfo, target: DbInfo) -> list[Statement]:
    """
    Generate the migration SQL of primary key, unique, and check constraints (add, drop, rename).
    """
    statements: list[str] = []

    for schema_name, table_name, src_table, dst_table in _iter_table_pairs(source, target):
        # Table dropped: its constraints are dropped with it.
        if dst_table is None:
            continue

        src_constraints = src_table.constraint_by_name if src_table else {}
        drops, renames, adds = _diff_constraints(
            schema_name=schema_name,
            table_name=table_name,
            src=src_constraints,
            dst=dst_table.constraint_by_name,
        )
        # Drops first (frees names), then renames, then adds.
        statements.extend(drops)
        statements.extend(renames)
        statements.extend(adds)

    return [Statement(Phase.CONSTRAINT, sql) for sql in statements]


def _generate_foreign_keys(*, source: DbInfo, target: DbInfo) -> list[Statement]:
    """
    Generate the migration SQL of foreign key constraints. Drops are phased before
    referenced objects are dropped; adds (with renames) after referenced tables and
    their keys exist.
    """
    fk_drops: list[str] = []
    fk_adds: list[str] = []

    for schema_name, table_name, src_table, dst_table in _iter_table_pairs(source, target):
        # Table dropped: its foreign keys are dropped with it.
        if dst_table is None:
            continue

        src_fks = src_table.foreign_key_by_name if src_table else {}
        drops, renames, adds = _diff_constraints(
            schema_name=schema_name,
            table_name=table_name,
            src=src_fks,
            dst=dst_table.foreign_key_by_name,
        )
        fk_drops.extend(drops)
        # Renames carry no referenced-object dependency, so they ride with the adds.
        fk_adds.extend(renames)
        fk_adds.extend(adds)

    return [Statement(Phase.FOREIGN_KEY_DROP, sql) for sql in fk_drops] + [
        Statement(Phase.FOREIGN_KEY_ADD, sql) for sql in fk_adds
    ]


def _generate_functions(*, source: DbInfo, target: DbInfo) -> list[Statement]:
    """
    Generate the migration SQL of functions and procedures. Creates (including
    CREATE OR REPLACE) are phased after tables so routine bodies can reference them;
    drops run early.
    """
    creates: list[str] = []
    drops: list[str] = []

    for schema_name, src_schema, dst_schema in _iter_schema_pairs(source, target):
        src_functions = src_schema.function_by_signature if src_schema else {}
        dst_functions = dst_schema.function_by_signature if dst_schema else {}

        for signature in sorted(src_functions.keys() | dst_functions.keys()):
            src_func = src_functions.get(signature)
            dst_func = dst_functions.get(signature)

            # Present in target only: create it.
            if src_func is None:
                # pg_get_functiondef has no trailing semicolon; add one to terminate the statement.
                creates.append(f"{dst_functions[signature].definition};")
            # Present in source only: drop it.
            elif dst_func is None:
                drops.append(
                    f"DROP {src_func.drop_keyword} {qualified(schema_name, src_func.name)}"
                    f"({src_func.identity_arguments});"
                )
            # Present in both: re-create if the definition changed.
            elif src_func.definition != dst_func.definition:
                # CREATE OR REPLACE cannot change the return type, so drop first when it differs.
                if src_func.return_type != dst_func.return_type:
                    drops.append(
                        f"DROP {src_func.drop_keyword} {qualified(schema_name, src_func.name)}"
                        f"({src_func.identity_arguments});"
                    )
                creates.append(f"{dst_func.definition};")

    return [Statement(Phase.FUNCTION_CREATE, sql) for sql in creates] + [
        Statement(Phase.FUNCTION_DROP, sql) for sql in drops
    ]


def _sequence_tail(sequence: Sequence) -> str:
    """
    Render the parameter tail shared by CREATE SEQUENCE.
    """
    tail = (
        f"AS {sequence.data_type}"
        f" INCREMENT BY {sequence.increment}"
        f" MINVALUE {sequence.min_value}"
        f" MAXVALUE {sequence.max_value}"
        f" START WITH {sequence.start}"
        f" CACHE {sequence.cache}"
    )
    if sequence.cycle:
        tail += " CYCLE"
    return tail


def _generate_sequences(*, source: DbInfo, target: DbInfo) -> list[Statement]:
    """
    Generate the migration SQL of standalone sequences. Creates and alters are phased
    before tables (a column default may reference a sequence); drops run after.
    """
    creates: list[str] = []
    drops: list[str] = []

    for schema_name, src_schema, dst_schema in _iter_schema_pairs(source, target):
        src_sequences = src_schema.sequence_by_name if src_schema else {}
        dst_sequences = dst_schema.sequence_by_name if dst_schema else {}

        for name in sorted(src_sequences.keys() | dst_sequences.keys()):
            # Present in target only: create it.
            if name not in src_sequences:
                creates.append(f"CREATE SEQUENCE {qualified(schema_name, name)} {_sequence_tail(dst_sequences[name])};")
            # Present in source only: drop it.
            elif name not in dst_sequences:
                drops.append(f"DROP SEQUENCE {qualified(schema_name, name)};")
            # Present in both: alter the parameters that differ.
            else:
                src_seq = src_sequences[name]
                dst_seq = dst_sequences[name]
                clauses: list[str] = []
                if src_seq.data_type != dst_seq.data_type:
                    clauses.append(f"AS {dst_seq.data_type}")
                if src_seq.increment != dst_seq.increment:
                    clauses.append(f"INCREMENT BY {dst_seq.increment}")
                if src_seq.min_value != dst_seq.min_value:
                    clauses.append(f"MINVALUE {dst_seq.min_value}")
                if src_seq.max_value != dst_seq.max_value:
                    clauses.append(f"MAXVALUE {dst_seq.max_value}")
                if src_seq.start != dst_seq.start:
                    clauses.append(f"START WITH {dst_seq.start}")
                if src_seq.cache != dst_seq.cache:
                    clauses.append(f"CACHE {dst_seq.cache}")
                if src_seq.cycle != dst_seq.cycle:
                    clauses.append("CYCLE" if dst_seq.cycle else "NO CYCLE")
                if clauses:
                    creates.append(f"ALTER SEQUENCE {qualified(schema_name, name)} {' '.join(clauses)};")

    return [Statement(Phase.SEQUENCE_CREATE, sql) for sql in creates] + [
        Statement(Phase.SEQUENCE_DROP, sql) for sql in drops
    ]


def generate_migration_sql(*, source: DbInfo, target: DbInfo) -> str:
    """
    Get the migration SQL between the given source and target databases.
    """
    # Collect statements by phase.
    statements_by_phase: dict[Phase, list[str]] = {phase: [] for phase in Phase}
    for generate in (
        _generate_schemas,
        _generate_extensions,
        _generate_sequences,
        _generate_tables,
        _generate_indexes,
        _generate_constraints,
        _generate_foreign_keys,
        _generate_functions,
    ):
        for statement in generate(source=source, target=target):
            statements_by_phase[statement.phase].append(statement.sql)

    # Join statements by phase, ordering by phase declaration order.
    return "\n".join(sql for phase in Phase for sql in statements_by_phase[phase])
