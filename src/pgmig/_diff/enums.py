from collections.abc import Iterator

from pgmig._diff._context import context
from pgmig._diff._core import Phase, Statement, ctx_iter_object_pairs, diff_comment_statements
from pgmig._errors import PgmigUnsupportedError
from pgmig._keys import ColumnKey, EnumKey
from pgmig._models import EnumType
from pgmig._sql import comment_on, ident, literal, qualified

# Suffix for the transient old type during a rewrite: the original is renamed aside so the
# target name is free for the recreated type, then dropped once every column is retyped.
_REWRITE_TMP_SUFFIX = "__pgmig_tmp"


def _enum_rename_value_statements(
    qualified_name: str, src_values: list[str], dst_values: list[str]
) -> list[str] | None:
    """
    Render ALTER TYPE ... RENAME VALUE statements for a pure positional rename.

    A pure rename keeps the enum's length and order: the lists match position-for-position
    except where a label was renamed one-for-one. To rule out reorders (which share length
    but reuse labels), every renamed-from label must vanish from the target and every
    renamed-to label must be new to the source. Returns None for anything else (differing
    length, reorder, mixed rename+insert), leaving it to the ADD VALUE path.
    """
    if len(src_values) != len(dst_values):
        return None

    # Caller only invokes this when the value lists differ, so an equal length guarantees
    # at least one differing position.
    diffs = [(old, new) for old, new in zip(src_values, dst_values, strict=True) if old != new]

    old_labels = {old for old, _ in diffs}
    new_labels = {new for _, new in diffs}
    if old_labels & set(dst_values) or new_labels & set(src_values):
        return None

    return [f"ALTER TYPE {qualified_name} RENAME VALUE {literal(old)} TO {literal(new)};" for old, new in diffs]


def _enum_add_value_statements(qualified_name: str, src_values: list[str], dst_values: list[str]) -> list[str] | None:
    """
    Render ALTER TYPE ... ADD VALUE statements for values added to an enum.

    Only additions are supported here: the source values must remain a subsequence of the
    target values (same relative order, values only inserted). Returns None when they are not
    a subsequence (a removal or reorder) so the caller can fall back to a type rewrite. Pure
    positional renames are handled earlier by _enum_rename_value_statements and never reach here.
    """
    target_iter = iter(dst_values)
    if not all(value in target_iter for value in src_values):
        return None

    src_set = set(src_values)
    statements: list[str] = []
    for index, value in enumerate(dst_values):
        if value in src_set:
            continue
        following = next((later for later in dst_values[index + 1 :] if later in src_set), None)
        if following is None:
            statements.append(f"ALTER TYPE {qualified_name} ADD VALUE {literal(value)};")
        else:
            statements.append(f"ALTER TYPE {qualified_name} ADD VALUE {literal(value)} BEFORE {literal(following)};")
    return statements


def _enum_rewrite_statements(schema_name: str, name: str, dst_enum: EnumType) -> Iterator[Statement]:
    """
    Rewrite an enum whose value list changed with no in-place ALTER form (a removal or
    reorder). Postgres has no DROP VALUE and no reorder primitive, so the type is dropped and
    recreated: rename the old type aside, create the new one with the target values, retype
    every dependent column through text, then drop the old type.

    The steps are split across phases (TYPE_CREATE -> TABLE -> TYPE_DROP) so the recipe orders
    correctly against other objects: a brand-new table using the type is built in TABLE after
    the recreate, and the old type survives (renamed) until every column has been retyped.

    Raises PgmigUnsupportedError for dependent shapes the rewrite cannot handle (generated,
    indexed, constrained, or view-read columns, and domains over the enum) rather than emit
    SQL that fails at apply. A removed value still present in data is not detected here: the
    USING cast fails loudly at apply, which pgmig does not prevent (it does not scan data).
    """
    qualified_name = qualified(schema_name, name)
    tmp_qualified = qualified(schema_name, name + _REWRITE_TMP_SUFFIX)
    dependencies = context.source.enum_column_dependencies.get(EnumKey(schema_name, name), [])

    # A domain whose base type is this enum would break on the recreate and its columns are
    # invisible to the column-dependency join. The enum renders schema-qualified via
    # format_type (introspection runs with a restricted search_path), matching data_type.
    enum_type_names = {f"{schema_name}.{name}", f"{schema_name}.{name}[]"}
    for schema in context.source.schema_by_name.values():
        for domain in schema.domain_by_name.values():
            if domain.data_type in enum_type_names:
                raise PgmigUnsupportedError(
                    f"Unsupported enum change for {qualified_name}: value removal/reorder requires a type "
                    f"rewrite, but domain {qualified(schema_name, domain.name)} is defined over the enum."
                )

    # Columns read by a view or materialized view: Postgres refuses ALTER COLUMN TYPE while a
    # (mat)view reads the column, and the retyped-reader recreate path does not fire because the
    # column's type name is unchanged (only the enum's values changed).
    read_columns: set[ColumnKey] = set()
    for columns in context.source.view_column_dependencies.values():
        read_columns |= columns

    for dep in dependencies:
        column_ref = f"{qualified(dep.schema, dep.table)}.{ident(dep.column)}"
        if dep.is_generated:
            reason = "it is a generated column"
        elif dep.in_index:
            reason = "it is used by an index"
        elif dep.in_constraint:
            reason = "it is used by a constraint"
        elif ColumnKey(dep.schema, dep.table, dep.column) in read_columns:
            reason = "it is read by a view or materialized view"
        else:
            continue
        raise PgmigUnsupportedError(
            f"Unsupported enum change for {qualified_name}: value removal/reorder requires rewriting "
            f"dependent column {column_ref}, but {reason}."
        )

    # Rename the old type aside and recreate the target type under the original name.
    yield Statement(Phase.TYPE_CREATE, f"ALTER TYPE {qualified_name} RENAME TO {ident(name + _REWRITE_TMP_SUFFIX)};")
    values = ", ".join(literal(value) for value in dst_enum.values)
    yield Statement(Phase.TYPE_CREATE, f"CREATE TYPE {qualified_name} AS ENUM ({values});")
    # Re-apply the comment: the recreate drops it, and the comment sync only fires on a change,
    # so an unchanged comment would otherwise be lost.
    if dst_enum.comment is not None:
        yield Statement(Phase.TYPE_CREATE, comment_on("TYPE", qualified_name, dst_enum.comment))

    # Retype each dependent column through text. A default is dropped first and re-added after,
    # since it references the old type and would not survive the type change cleanly.
    for dep in dependencies:
        column = context.source.schema_by_name[dep.schema].table_by_name[dep.table].column_by_name[dep.column]
        prefix = f"ALTER TABLE {qualified(dep.schema, dep.table)} ALTER COLUMN {ident(dep.column)}"
        if column.default is not None:
            yield Statement(Phase.TABLE, f"{prefix} DROP DEFAULT;")
        text_type = "text[]" if dep.is_array else "text"
        yield Statement(
            Phase.TABLE, f"{prefix} TYPE {column.type} USING {ident(dep.column)}::{text_type}::{column.type};"
        )
        if column.default is not None:
            yield Statement(Phase.TABLE, f"{prefix} SET DEFAULT {column.default};")

    # Drop the old type once no column references it.
    yield Statement(Phase.TYPE_DROP, f"DROP TYPE {tmp_qualified};")


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of enum types (create, drop, ADD VALUE). Creates and
    value additions are phased before tables (a column may be of the type); drops run
    after.
    """
    for schema_name, src_enums, dst_enums, pairs in ctx_iter_object_pairs(lambda schema: schema.enum_by_name):
        for name, src_enum, dst_enum in pairs:
            qualified_name = qualified(schema_name, name)

            # Present in target only: create it.
            if src_enum is None:
                values = ", ".join(literal(value) for value in dst_enums[name].values)
                yield Statement(
                    Phase.TYPE_CREATE,
                    f"CREATE TYPE {qualified_name} AS ENUM ({values});",
                )
            # Present in source only: drop it.
            elif dst_enum is None:
                yield Statement(Phase.TYPE_DROP, f"DROP TYPE {qualified_name};")
            # Present in both: rename values in place, else add new ones, else (removal or
            # reorder, which have no in-place ALTER form) rewrite the type.
            elif src_enum.values != dst_enum.values:
                statements = _enum_rename_value_statements(qualified_name, src_enum.values, dst_enum.values)
                if statements is None:
                    statements = _enum_add_value_statements(qualified_name, src_enum.values, dst_enum.values)
                if statements is None:
                    yield from _enum_rewrite_statements(schema_name, name, dst_enum)
                else:
                    for sql in statements:
                        yield Statement(Phase.TYPE_CREATE, sql)

        # Sync comments for target enums, after the types they annotate exist.
        for sql in diff_comment_statements(schema_name, src_enums, dst_enums, kind="TYPE"):
            yield Statement(Phase.TYPE_CREATE, sql)
