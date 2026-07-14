from collections.abc import Iterator

from pgmig._diff._core import Phase, Statement, ctx_iter_object_pairs, diff_comment_statements
from pgmig._sql import ident, qualified


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of composite types (create, drop). Creates are phased before
    tables (a column may be of the type); drops run after. A field-level change on a type
    present in both sides is not supported yet (ALTER TYPE deferred) and raises.
    """
    for schema_name, src_types, dst_types, pairs in ctx_iter_object_pairs(lambda schema: schema.composite_type_by_name):
        for name, src_type, dst_type in pairs:
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
        for sql in diff_comment_statements(schema_name, src_types, dst_types, kind="TYPE"):
            yield Statement(Phase.TYPE_CREATE, sql)
