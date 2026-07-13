from collections.abc import Iterator

from pgmig._diff._core import Context, Phase, Statement, _diff_comments, _iter_schema_pairs
from pgmig._models import EnumType
from pgmig._sql import comment_on, literal, schema_qualified


def _enum_add_value_statements(qualified_name: str, src_values: list[str], dst_values: list[str]) -> list[str]:
    """
    Render ALTER TYPE ... ADD VALUE statements for values added to an enum.

    Only additions are supported: the source values must remain a subsequence of the
    target values (same relative order, values only inserted). A removal, reorder, or
    renamed-looking label raises NotImplementedError rather than emitting a wrong or
    non-converging migration.
    """
    target_iter = iter(dst_values)
    if not all(value in target_iter for value in src_values):
        raise NotImplementedError(
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


def _enum_comment_statements(schema_name: str, src: dict[str, EnumType], dst: dict[str, EnumType]) -> list[str]:
    """
    Emit COMMENT ON TYPE for target enums whose comment differs from source.
    """
    return _diff_comments(
        src, dst, render=lambda name, enum: comment_on("TYPE", schema_qualified(schema_name, name), enum.comment)
    )


def generate(ctx: Context) -> Iterator[Statement]:
    """
    Generate the migration SQL of enum types (create, drop, ADD VALUE). Creates and
    value additions are phased before tables (a column may be of the type); drops run
    after.
    """
    for schema_name, src_schema, dst_schema in _iter_schema_pairs(ctx.source, ctx.target):
        src_enums = src_schema.enum_by_name if src_schema else {}
        dst_enums = dst_schema.enum_by_name if dst_schema else {}

        for name in sorted(src_enums.keys() | dst_enums.keys()):
            src_enum = src_enums.get(name)
            dst_enum = dst_enums.get(name)
            qualified_name = schema_qualified(schema_name, name)

            # Present in target only: create it.
            if src_enum is None:
                values = ", ".join(literal(value) for value in dst_enums[name].values)
                yield Statement(Phase.TYPE_CREATE, f"CREATE TYPE {qualified_name} AS ENUM ({values});")
            # Present in source only: drop it.
            elif dst_enum is None:
                yield Statement(Phase.TYPE_DROP, f"DROP TYPE {qualified_name};")
            # Present in both: add any new values (removal/reorder/rename unsupported).
            elif src_enum.values != dst_enum.values:
                for sql in _enum_add_value_statements(qualified_name, src_enum.values, dst_enum.values):
                    yield Statement(Phase.TYPE_CREATE, sql)

        # Sync comments for target enums, after the types they annotate exist.
        for sql in _enum_comment_statements(schema_name, src_enums, dst_enums):
            yield Statement(Phase.TYPE_CREATE, sql)
