from collections.abc import Iterator

from pgmig._diff._context import context
from pgmig._diff._core import Phase, Statement, _diff_comments, ctx_iter_table_pairs, diff_single_comment
from pgmig._errors import PgmigUnsupportedError
from pgmig._models import Column, Table
from pgmig._sql import comment_on, ident, qualified


def _table_owner_statements(schema_name: str, src_table: Table | None, dst_table: Table) -> list[str]:
    """
    Emit ALTER TABLE ... OWNER TO when a table present on both sides has a different
    owner than the target.

    Ownership of a newly created table (absent source) is not managed: it is left owned
    by the role running the migration, so nothing is emitted here. Such a table only
    reconciles to the target owner on a later run, once it exists on both sides and this
    same-owner comparison applies.

    With --ignore-owner, ownership reconciliation is skipped entirely.
    """
    if context.ignore_owner or src_table is None or src_table.owner == dst_table.owner:
        return []
    return [f"ALTER TABLE {qualified(schema_name, dst_table.name)} OWNER TO {ident(dst_table.owner)};"]


def _parenthesize_generation(expression: str) -> str:
    """
    Wrap a generation expression in exactly one pair of outer parentheses, as the GENERATED
    ALWAYS AS (...) STORED syntax requires. pg_get_expr parenthesizes inconsistently -- it
    wraps a top-level operator expression ("(a * b)") but not a bare column ("b") or function
    call ("upper(x)") -- so strip a redundant wrapping pair if one already spans the whole
    expression, then add our own.
    """
    inner = expression
    if inner.startswith("(") and inner.endswith(")"):
        depth = 0
        for index, char in enumerate(inner):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                # The opening paren closes before the end, so it does not wrap the whole
                # expression (e.g. "(a) + (b)") -- leave it untouched.
                if depth == 0 and index != len(inner) - 1:
                    break
        else:
            inner = inner[1:-1]
    return f"({inner})"


def _column_def(column: Column) -> str:
    """
    Render a column for CREATE TABLE / ADD COLUMN, with NOT NULL and DEFAULT inline.
    """
    # A serial column expands to its pseudo-type; the integer type, nextval()
    # default and NOT NULL are all implied and must not be emitted alongside it.
    if column.serial_type is not None:
        return f"{ident(column.name)} {column.serial_type}"

    # An identity column expands to its GENERATED ... AS IDENTITY clause; the identity
    # implies NOT NULL and owns its backing sequence, both of which must not be emitted
    # alongside it (mirrors the serial pseudo-type above).
    if column.identity_clause is not None:
        return f"{ident(column.name)} {column.type} {column.identity_clause}"

    # A generated column carries its expression as a GENERATED ALWAYS AS (...) clause, not a
    # DEFAULT, followed by STORED or VIRTUAL (VIRTUAL is PG18+). A generated column may still
    # be NOT NULL, appended after the clause.
    if column.generated in ("s", "v"):
        expression = _parenthesize_generation(column.generation_expression or "")
        storage = "STORED" if column.generated == "s" else "VIRTUAL"
        clause = f"{ident(column.name)} {column.type} GENERATED ALWAYS AS {expression} {storage}"
        return f"{clause} NOT NULL" if column.not_null else clause

    parts = [f"{ident(column.name)} {column.type}"]
    if column.default is not None:
        parts.append(f"DEFAULT {column.default}")
    if column.not_null:
        parts.append("NOT NULL")
    return " ".join(parts)


def _create_table(schema_name: str, table: Table) -> list[str]:
    """
    Render the CREATE TABLE statement for a target-only table.

    A partition is created with PARTITION OF (no column list -- columns are inherited from
    the parent); a partitioned parent (or a sub-partitioned partition) carries a trailing
    PARTITION BY clause.

    A partition child may be UNLOGGED independently of its (always-logged) parent, so the
    keyword is emitted on both the plain and PARTITION OF forms.
    """
    keyword = "UNLOGGED TABLE" if table.unlogged else "TABLE"
    if table.partition_parent is not None:
        parent_schema, parent_name = table.partition_parent
        statement = (
            f"CREATE {keyword} {qualified(schema_name, table.name)} "
            f"PARTITION OF {qualified(parent_schema, parent_name)} {table.partition_bound}"
        )
        if table.is_partitioned:
            statement += f" PARTITION BY {table.partition_key}"
        return [f"{statement};"]

    columns = ", ".join(_column_def(column) for column in table.columns)
    partition_by = f" PARTITION BY {table.partition_key}" if table.is_partitioned else ""
    return [f"CREATE {keyword} {qualified(schema_name, table.name)} ({columns}){partition_by};"]


def _attach_partition(schema_name: str, table_name: str, parent: tuple[str, str], bound: str | None) -> str:
    """
    ALTER TABLE <parent> ATTACH PARTITION <child> <bound> -- make an existing standalone
    table a partition.
    """
    parent_schema, parent_name = parent
    return (
        f"ALTER TABLE {qualified(parent_schema, parent_name)} "
        f"ATTACH PARTITION {qualified(schema_name, table_name)} {bound};"
    )


def _detach_partition(schema_name: str, table_name: str, parent: tuple[str, str]) -> str:
    """
    ALTER TABLE <parent> DETACH PARTITION <child> -- turn a partition back into a
    standalone table (the table itself survives).
    """
    parent_schema, parent_name = parent
    return f"ALTER TABLE {qualified(parent_schema, parent_name)} DETACH PARTITION {qualified(schema_name, table_name)};"


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
    shared column sync TYPE, then DEFAULT, then NOT NULL. An identity or serial change is
    unsupported and raises rather than emitting a silently-empty (falsely converged)
    migration.

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
            column_statements, column_deferred = _alter_shared_column(
                schema_name=schema_name,
                table_name=table_name,
                column_name=column_name,
                src_column=src_columns[column_name],
                dst_column=dst_columns[column_name],
                pk_columns=pk_columns,
                src_pk_columns=src_pk_columns,
            )
            statements.extend(column_statements)
            deferred_drop_not_null.extend(column_deferred)
    return statements, deferred_drop_not_null


def _alter_shared_column(
    *,
    schema_name: str,
    table_name: str,
    column_name: str,
    src_column: Column,
    dst_column: Column,
    pk_columns: set[str],
    src_pk_columns: set[str],
) -> tuple[list[str], list[str]]:
    """
    Sync one column present on both sides: TYPE, then DEFAULT, then NOT NULL, with the
    identity ADD/SET/DROP interleaved in the order Postgres requires. An identity or serial
    change that cannot be expressed raises rather than emitting a silently-empty diff.

    Returns (statements, deferred_drop_not_null) for this column; see `_alter_columns` for
    why a DROP NOT NULL on a source-PK column is deferred past the CONSTRAINT phase.
    """
    statements: list[str] = []
    deferred_drop_not_null: list[str] = []
    identity_changed = src_column.identity != dst_column.identity
    # A serial change keeps the integer type, so the type guard does not fire. The
    # serial backing sequence is excluded from introspection, so emitting SET
    # DEFAULT nextval('..._seq') would reference a sequence that is never created
    # (apply fails "relation does not exist"). Refuse rather than emit a
    # non-converging diff -- EXCEPT a serial *source* converting to an identity
    # target, which is supported below (its nextval() default is dropped and the
    # identity creates its own sequence). That single case is a serial change with
    # a non-serial target reached via an identity change, so it is let through.
    serial_changed = src_column.serial_type != dst_column.serial_type
    if serial_changed and (dst_column.serial_type is not None or not identity_changed):
        raise PgmigUnsupportedError(
            f"Column serial change is not supported: "
            f"{qualified(schema_name, table_name)}.{ident(column_name)} "
            f"{src_column.serial_type} -> {dst_column.serial_type}"
        )
    # A generated-ness change (plain <-> generated, or STORED <-> VIRTUAL) has no in-place
    # ALTER and is potentially destructive (Postgres has no ADD GENERATED, and switching
    # storage rebuilds the column), so it still raises rather than mis-diff. A generated
    # column's `default` is None on both sides, so the DEFAULT sync below is inert.
    if src_column.generated != dst_column.generated:
        raise PgmigUnsupportedError(
            f"Column generated change is not supported: {qualified(schema_name, table_name)}.{ident(column_name)}"
        )
    # A generation-expression change on a column that keeps the same generated kind is
    # supported. A STORED column's data is derived, so it is rebuilt non-destructively with
    # DROP COLUMN + ADD COLUMN (portable to pre-PG18, which has no in-place expression ALTER);
    # the re-added definition carries the new expression, type and NOT NULL, so no further
    # per-column sync is needed. A VIRTUAL column (PG18+) has no stored data and changes in
    # place with SET EXPRESSION AS (...), handled after the type change below.
    expression_changed = (
        src_column.generated != "" and src_column.generation_expression != dst_column.generation_expression
    )
    if expression_changed and src_column.generated == "s":
        table_prefix = f"ALTER TABLE {qualified(schema_name, table_name)}"
        return (
            [
                f"{table_prefix} DROP COLUMN {ident(column_name)};",
                f"{table_prefix} ADD COLUMN {_column_def(dst_column)};",
            ],
            [],
        )
    prefix = f"ALTER TABLE {qualified(schema_name, table_name)} ALTER COLUMN {ident(column_name)}"
    # Emit order matters: drops before adds. Postgres refuses ADD IDENTITY on a
    # column that still has a default, and refuses SET DEFAULT on a column that is
    # still an identity. So: TYPE, then DROP IDENTITY, then DROP DEFAULT, then the
    # identity ADD/SET, then SET DEFAULT, then NOT NULL.
    #
    # Type change first: a widened type must be in place before a dependent
    # default or NOT NULL is (re)applied. A USING col::newtype cast is emitted so
    # conversions needing an explicit cast (text -> integer, varchar -> enum,
    # timezone changes) converge; the explicit cast is a superset of the implicit
    # assignment cast, so it never regresses. A pair with no cast at all fails
    # loudly at apply -- a visible error, not a silent divergence.
    #
    # A generated column is the exception: Postgres recomputes it from its
    # expression on a type change and refuses USING ("cannot specify USING when
    # altering type of generated column"), so the USING clause is omitted for it.
    if src_column.type != dst_column.type:
        if dst_column.generated != "":
            statements.append(f"{prefix} TYPE {dst_column.type};")
        else:
            statements.append(f"{prefix} TYPE {dst_column.type} USING {ident(column_name)}::{dst_column.type};")
    # A VIRTUAL generated column's expression is changed in place (PG18+); STORED is rebuilt
    # via DROP + ADD above, which returns early, so only VIRTUAL reaches here.
    if expression_changed:
        expression = _parenthesize_generation(dst_column.generation_expression or "")
        statements.append(f"{prefix} SET EXPRESSION AS {expression};")
    if identity_changed and dst_column.identity_kind is None:
        # Loses its identity. The owned identity sequence drops with it; the
        # column stays NOT NULL (handled by the NOT NULL block below).
        statements.append(f"{prefix} DROP IDENTITY;")
    if dst_column.default is None and src_column.default is not None:
        # Drop the old default before any ADD IDENTITY. For a serial source this
        # is the nextval() default; its owned sequence lingers (excluded from
        # introspection) but the diff still converges.
        statements.append(f"{prefix} DROP DEFAULT;")
    if identity_changed and dst_column.identity_kind is not None:
        if src_column.identity_kind is None:
            # Gains an identity. ADD ... AS IDENTITY requires the column to already
            # be NOT NULL, so set it first when the source was nullable (the generic
            # NOT NULL block below is skipped for identity targets, so no double).
            if not src_column.not_null:
                statements.append(f"{prefix} SET NOT NULL;")
            statements.append(f"{prefix} ADD {dst_column.identity_clause};")
        else:
            # Stays an identity, generation kind flips (ALWAYS <-> BY DEFAULT).
            statements.append(f"{prefix} SET GENERATED {dst_column.identity_kind};")
    if dst_column.default is not None and src_column.default != dst_column.default:
        statements.append(f"{prefix} SET DEFAULT {dst_column.default};")
    if src_column.not_null != dst_column.not_null:
        if dst_column.not_null:
            # Skip if a target primary key or the target identity already implies
            # NOT NULL for this column.
            if column_name not in pk_columns and dst_column.identity_kind is None:
                statements.append(f"{prefix} SET NOT NULL;")
        elif column_name in src_pk_columns:
            # Covering source PK drops this run; defer past the CONSTRAINT phase.
            deferred_drop_not_null.append(f"{prefix} DROP NOT NULL;")
        else:
            statements.append(f"{prefix} DROP NOT NULL;")
    return statements, deferred_drop_not_null


def _persistence_statements(schema_name: str, src_table: Table, dst_table: Table) -> list[str]:
    """
    Emit ALTER TABLE ... SET LOGGED / SET UNLOGGED when a table's durability flips between
    sides. Applies to plain tables and partition children alike (a partitioned parent is
    always logged, so it never flips here).
    """
    if src_table.unlogged == dst_table.unlogged:
        return []
    action = "SET UNLOGGED" if dst_table.unlogged else "SET LOGGED"
    return [f"ALTER TABLE {qualified(schema_name, dst_table.name)} {action};"]


def _table_comment_statements(schema_name: str, src_table: Table | None, dst_table: Table) -> list[str]:
    """
    Emit COMMENT ON TABLE when the comment differs (absent source table = no comment).
    """
    return diff_single_comment(
        src_table,
        dst_table,
        render=lambda table: comment_on("TABLE", qualified(schema_name, table.name), table.comment),
    )


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


def _partition_depth(key: tuple[str, str], table_map: dict[tuple[str, str], Table]) -> int:
    """
    Depth of a table in the partition hierarchy (0 = root / not a partition), walking the
    partition_parent chain within `table_map`. Sorting creates by depth guarantees a
    parent is created before its partitions (and sub-partitions).
    """
    depth = 0
    seen: set[tuple[str, str]] = set()
    table: Table | None = table_map.get(key)
    while table is not None and table.partition_parent is not None and table.partition_parent not in seen:
        seen.add(table.partition_parent)
        depth += 1
        table = table_map.get(table.partition_parent)
    return depth


def _membership_statements(schema_name: str, table_name: str, src_table: Table, dst_table: Table) -> list[str]:
    """
    Statements reconciling a table's partition membership across the diff: ATTACH a
    standalone table, DETACH a partition, or re-parent (detach + attach). Changes Postgres
    cannot make in place -- partition key/strategy, or a bound change on the same parent --
    raise rather than emit a data-destructive DROP + CREATE.
    """
    if (src_table.is_partitioned or dst_table.is_partitioned) and (
        src_table.partition_strategy != dst_table.partition_strategy
        or src_table.partition_key != dst_table.partition_key
    ):
        raise PgmigUnsupportedError(
            f"Partition key/strategy change is not supported: {qualified(schema_name, table_name)}"
        )

    src_parent = src_table.partition_parent
    dst_parent = dst_table.partition_parent
    if src_parent is not None and dst_parent is not None:
        if src_parent != dst_parent:
            # Re-parent: detach from the old parent, attach to the new one.
            return [
                _detach_partition(schema_name, table_name, src_parent),
                _attach_partition(schema_name, table_name, dst_parent, dst_table.partition_bound),
            ]
        if src_table.partition_bound != dst_table.partition_bound:
            raise PgmigUnsupportedError(
                f"Partition bound change is not supported: {qualified(schema_name, table_name)}"
            )
        return []
    if src_parent is not None:
        return [_detach_partition(schema_name, table_name, src_parent)]
    if dst_parent is not None:
        return [_attach_partition(schema_name, table_name, dst_parent, dst_table.partition_bound)]
    return []


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of tables: create, alter, or drop, plus partition
    attach/detach and table/column comment sync.

    Emission order within the TABLE phase is create -> alter -> drop, and creates are
    ordered parent-before-child, so a partition is always created after (or attached to) an
    existing parent. Dropping a partitioned parent cascades to its partitions, so a
    partition whose parent is also dropped is skipped.
    """
    pairs = list(ctx_iter_table_pairs())
    src_map = {(schema, name): src for schema, name, src, _dst in pairs if src is not None}
    dst_map = {(schema, name): dst for schema, name, _src, dst in pairs if dst is not None}

    creates: list[tuple[str, str, Table]] = []
    alters: list[tuple[str, str, Table, Table]] = []
    drops: list[tuple[str, str]] = []
    for schema_name, table_name, src_table, dst_table in pairs:
        if dst_table is None:
            drops.append((schema_name, table_name))
        elif src_table is None:
            creates.append((schema_name, table_name, dst_table))
        else:
            alters.append((schema_name, table_name, src_table, dst_table))

    # Create: parent before child (and comments; a new table has no source owner to sync).
    creates.sort(key=lambda item: (_partition_depth((item[0], item[1]), dst_map), item[0], item[1]))
    for schema_name, _table_name, dst_table in creates:
        rendered = _create_table(schema_name, dst_table)
        rendered += _table_comment_statements(schema_name, None, dst_table)
        rendered += _column_comment_statements(schema_name, None, dst_table)
        for sql in rendered:
            yield Statement(Phase.TABLE, sql)

    # Alter: membership transitions, then columns (skipped for a partition child, whose
    # columns are inherited), then owner and comments.
    for schema_name, table_name, src_table, dst_table in alters:
        rendered = _membership_statements(schema_name, table_name, src_table, dst_table)
        # Persistence flip applies to partition children too, so it is outside the
        # is_partition column-diff gate below.
        rendered += _persistence_statements(schema_name, src_table, dst_table)
        deferred_drop_not_null: list[str] = []
        if not dst_table.is_partition:
            column_statements, deferred_drop_not_null = _alter_columns(
                schema_name=schema_name,
                table_name=table_name,
                src_table=src_table,
                dst_table=dst_table,
                pk_columns=dst_table.get_primary_key_columns(),
                src_pk_columns=src_table.get_primary_key_columns(),
            )
            rendered += column_statements
        rendered += _table_owner_statements(schema_name, src_table, dst_table)
        rendered += _table_comment_statements(schema_name, src_table, dst_table)
        rendered += _column_comment_statements(schema_name, src_table, dst_table)
        for sql in rendered:
            yield Statement(Phase.TABLE, sql)
        # DROP NOT NULL for a column whose covering primary key drops this run must run
        # after the CONSTRAINT-phase DROP CONSTRAINT.
        for sql in deferred_drop_not_null:
            yield Statement(Phase.COLUMN_DROP_NOT_NULL, sql)

    # Drop: skip a partition whose parent is also dropped (the parent's DROP TABLE
    # cascades to it). Attached objects are dropped with the table.
    for schema_name, table_name in drops:
        parent = src_map[schema_name, table_name].partition_parent
        if parent is not None and parent in src_map and parent not in dst_map:
            continue
        yield Statement(Phase.TABLE, f"DROP TABLE {qualified(schema_name, table_name)};")
