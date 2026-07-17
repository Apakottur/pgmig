from collections.abc import Iterator

from pgmig._diff._context import context
from pgmig._diff._core import (
    Phase,
    Statement,
    collect_relations,
    ctx_iter_object_pairs,
    diff_comment_statements,
    topological_drop_order,
    topological_sort,
)
from pgmig._errors import PgmigUnsupportedError
from pgmig._keys import CompositeTypeKey
from pgmig._sql import ident, qualified


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of composite types (create, drop). Creates are phased before
    tables (a column may be of the type); drops run after. A field-level change on a type
    present in both sides is not supported yet (ALTER TYPE deferred) and raises.

    A composite type whose field is another composite type must be created after, and dropped
    before, the type it references. Creates are topologically ordered dependencies-first over
    the target graph; drops are ordered dependents-first (the reverse) over the source graph.
    """
    source, target = context.source, context.target
    src_types = collect_relations(source, lambda schema: schema.composite_type_by_name, CompositeTypeKey)
    dst_types = collect_relations(target, lambda schema: schema.composite_type_by_name, CompositeTypeKey)

    # Present in both with differing fields: ALTER TYPE is not supported yet.
    for key in src_types.keys() & dst_types.keys():
        if src_types[key].fields != dst_types[key].fields:
            raise PgmigUnsupportedError(
                f"Composite type field change is not supported: {qualified(key.schema, key.name)} "
                f"({src_types[key].fields} -> {dst_types[key].fields})"
            )

    # Creates: dependencies-first over the target graph.
    create_keys = dst_types.keys() - src_types.keys()
    for key in topological_sort(create_keys, target.composite_type_dependencies):
        fields = ", ".join(f"{ident(field.name)} {field.type}" for field in dst_types[key].fields)
        yield Statement(Phase.TYPE_CREATE, f"CREATE TYPE {qualified(key.schema, key.name)} AS ({fields});")

    # Drops: dependents-first over the source graph.
    drop_keys = src_types.keys() - dst_types.keys()
    for key in topological_drop_order(drop_keys, source.composite_type_dependencies):
        yield Statement(Phase.TYPE_DROP, f"DROP TYPE {qualified(key.schema, key.name)};")

    # Sync comments for target composite types, after the types they annotate exist.
    for schema_name, src_schema_types, dst_schema_types, _pairs in ctx_iter_object_pairs(
        lambda schema: schema.composite_type_by_name
    ):
        for sql in diff_comment_statements(schema_name, src_schema_types, dst_schema_types, kind="TYPE"):
            yield Statement(Phase.TYPE_CREATE, sql)
