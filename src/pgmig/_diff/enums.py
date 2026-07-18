from collections.abc import Iterator

from pgmig._diff._core import Phase, Statement, ctx_iter_object_pairs, diff_comment_statements
from pgmig._errors import PgmigUnsupportedError
from pgmig._sql import literal, qualified


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


def _enum_add_value_statements(qualified_name: str, src_values: list[str], dst_values: list[str]) -> list[str]:
    """
    Render ALTER TYPE ... ADD VALUE statements for values added to an enum.

    Only additions are supported: the source values must remain a subsequence of the
    target values (same relative order, values only inserted). A removal, reorder, or
    renamed-looking label raises UnsupportedChangeError rather than emitting a wrong or
    non-converging migration. Pure positional renames are handled earlier by
    _enum_rename_value_statements and never reach here.
    """
    target_iter = iter(dst_values)
    if not all(value in target_iter for value in src_values):
        raise PgmigUnsupportedError(
            f"Unsupported enum change for {qualified_name}: values may only be appended or inserted, "
            f"not removed, reordered, or renamed ({src_values} -> {dst_values})."
        )

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
            # Present in both: rename values in place, else add new ones (removal/reorder/
            # mixed rename+insert unsupported).
            elif src_enum.values != dst_enum.values:
                statements = _enum_rename_value_statements(qualified_name, src_enum.values, dst_enum.values)
                if statements is None:
                    statements = _enum_add_value_statements(qualified_name, src_enum.values, dst_enum.values)
                for sql in statements:
                    yield Statement(Phase.TYPE_CREATE, sql)

        # Sync comments for target enums, after the types they annotate exist.
        for sql in diff_comment_statements(schema_name, src_enums, dst_enums, kind="TYPE"):
            yield Statement(Phase.TYPE_CREATE, sql)
