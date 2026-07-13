from collections.abc import Iterator

from pgmig._diff._core import Context, Phase, Statement, _diff_comments, _iter_schema_pairs
from pgmig._models import CompositeType
from pgmig._sql import comment_on, ident, qualified


def _composite_comment_statements(
    schema_name: str, src: dict[str, CompositeType], dst: dict[str, CompositeType]
) -> list[str]:
    """
    Emit COMMENT ON TYPE for target composite types whose comment differs from source.
    """
    return _diff_comments(
        src, dst, render=lambda name, ct: comment_on("TYPE", qualified(schema_name, name), ct.comment)
    )


def generate(ctx: Context) -> Iterator[Statement]:
    """
    Generate the migration SQL of composite types (create, drop). Creates are phased before
    tables (a column may be of the type); drops run after. A field-level change on a type
    present in both sides is not supported yet (ALTER TYPE deferred) and raises.
    """
    for schema_name, src_schema, dst_schema in _iter_schema_pairs(ctx.source, ctx.target):
        src_types = src_schema.composite_type_by_name if src_schema else {}
        dst_types = dst_schema.composite_type_by_name if dst_schema else {}

        for name in sorted(src_types.keys() | dst_types.keys()):
            src_type = src_types.get(name)
            dst_type = dst_types.get(name)
            qualified_name = qualified(schema_name, name)

            # Present in target only: create it.
            if src_type is None:
                fields = ", ".join(f"{ident(field.name)} {field.type}" for field in dst_types[name].fields)
                yield Statement(Phase.TYPE_CREATE, f"CREATE TYPE {qualified_name} AS ({fields});")
            # Present in source only: drop it.
            elif dst_type is None:
                yield Statement(Phase.TYPE_DROP, f"DROP TYPE {qualified_name};")
            # Present in both with differing fields: ALTER TYPE is not supported yet.
            elif src_type.fields != dst_type.fields:
                raise NotImplementedError(
                    f"Composite type field change is not supported: {qualified_name} "
                    f"({src_type.fields} -> {dst_type.fields})"
                )

        # Sync comments for target composite types, after the types they annotate exist.
        for sql in _composite_comment_statements(schema_name, src_types, dst_types):
            yield Statement(Phase.TYPE_CREATE, sql)
