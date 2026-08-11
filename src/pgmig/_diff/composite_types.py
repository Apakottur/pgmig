from collections.abc import Iterator

from pgmig._diff._context import context
from pgmig._diff._core import (
    Phase,
    Statement,
    collect_relations,
    ctx_iter_object_pairs,
    diff_comment_statements,
    owner_statements,
    topological_drop_order,
    topological_sort,
)
from pgmig._errors import PgmigUnsupportedError
from pgmig._keys import CompositeTypeKey
from pgmig._models import CompositeType
from pgmig._sql import ident, qualified


def _alter_attribute_statements(qualified_name: str, source: CompositeType, target: CompositeType) -> list[str]:
    """
    Render ALTER TYPE ... {DROP,ALTER,ADD} ATTRIBUTE statements for a composite type present on
    both sides. Attributes are matched by name: a name present only in source is dropped, only in
    target is added, and one present on both with a differing type is retyped. CASCADE propagates
    each change to any table row type that uses the type (Postgres refuses the alter otherwise).

    Reordering surviving attributes has no ALTER form -- ADD ATTRIBUTE only appends -- so a change
    that would leave the surviving attributes in a different relative order, or that interleaves an
    added attribute among survivors, cannot converge and raises UnsupportedChangeError.
    """
    src_by_name = {field.name: field for field in source.fields}
    dst_by_name = {field.name: field for field in target.fields}

    # ADD only appends, so the achievable result is the surviving source attributes in their
    # original order followed by the additions. If the target orders them any other way it is a
    # reorder we cannot express.
    survivors = [field.name for field in source.fields if field.name in dst_by_name]
    additions = [field.name for field in target.fields if field.name not in src_by_name]
    if survivors + additions != [field.name for field in target.fields]:
        raise PgmigUnsupportedError(
            f"Composite type attribute reorder is not supported: {qualified_name} "
            f"({[field.name for field in source.fields]} -> {[field.name for field in target.fields]})"
        )

    # Drops first (frees the removed names), then type changes, then additions.
    drops = [
        f"ALTER TYPE {qualified_name} DROP ATTRIBUTE {ident(field.name)} CASCADE;"
        for field in source.fields
        if field.name not in dst_by_name
    ]
    type_changes = [
        f"ALTER TYPE {qualified_name} ALTER ATTRIBUTE {ident(field.name)} TYPE {field.type} CASCADE;"
        for field in target.fields
        if field.name in src_by_name and src_by_name[field.name].type != field.type
    ]
    additions_sql = [
        f"ALTER TYPE {qualified_name} ADD ATTRIBUTE {ident(field.name)} {field.type} CASCADE;"
        for field in target.fields
        if field.name not in src_by_name
    ]
    return drops + type_changes + additions_sql


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of composite types (create, drop, attribute alters). Creates and
    attribute changes are phased before tables (a column may be of the type); drops run after. A
    field difference on a type present in both sides becomes in-place ALTER TYPE ... ATTRIBUTE
    statements; only a surviving-attribute reorder remains unsupported.

    A composite type whose field is another composite type must be created after, and dropped
    before, the type it references. Creates are topologically ordered dependencies-first over
    the target graph; drops are ordered dependents-first (the reverse) over the source graph.
    """
    source, target = context.source, context.target
    src_types = collect_relations(source, lambda schema: schema.composite_type_by_name, CompositeTypeKey)
    dst_types = collect_relations(target, lambda schema: schema.composite_type_by_name, CompositeTypeKey)

    # Creates: dependencies-first over the target graph.
    create_keys = dst_types.keys() - src_types.keys()
    for key in topological_sort(create_keys, target.composite_type_dependencies):
        fields = ", ".join(f"{ident(field.name)} {field.type}" for field in dst_types[key].fields)
        yield Statement(
            Phase.TYPE_CREATE,
            f"CREATE TYPE {qualified(key.schema, key.name)} AS ({fields});",
        )

    # Present in both with differing fields: alter attributes in place. Emitted after creates so an
    # added attribute may reference a composite type created in this same migration (both are in
    # Phase.TYPE_CREATE, whose statements keep emission order).
    for key in sorted(src_types.keys() & dst_types.keys(), key=lambda k: (k.schema, k.name)):
        qualified_name = qualified(key.schema, key.name)
        if src_types[key].fields != dst_types[key].fields:
            for sql in _alter_attribute_statements(qualified_name, src_types[key], dst_types[key]):
                yield Statement(Phase.TYPE_CREATE, sql)
        # A composite type is altered in place (never recreated), so reconcile its ownership.
        for sql in owner_statements("TYPE", qualified_name, src_types[key].owner, dst_types[key].owner):
            yield Statement(Phase.TYPE_CREATE, sql)

    # Drops: dependents-first over the source graph.
    drop_keys = src_types.keys() - dst_types.keys()
    for key in topological_drop_order(drop_keys, source.composite_type_dependencies):
        yield Statement(Phase.TYPE_DROP, f"DROP TYPE {qualified(key.schema, key.name)};")

    # Sync comments for target composite types, after the types they annotate exist.
    for (
        schema_name,
        src_schema_types,
        dst_schema_types,
        _pairs,
    ) in ctx_iter_object_pairs(lambda schema: schema.composite_type_by_name):
        for sql in diff_comment_statements(schema_name, src_schema_types, dst_schema_types, kind="TYPE"):
            yield Statement(Phase.TYPE_CREATE, sql)
