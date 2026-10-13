from collections.abc import Callable, Mapping
from typing import TypeVar

from pgmig._keys import RelationKey
from pgmig._models import DbIntrospectionResult, Schema

_ObjT = TypeVar("_ObjT")
_KeyT = TypeVar("_KeyT")


def collect_relations(
    db_introspection_result: DbIntrospectionResult,
    select: Callable[[Schema], Mapping[str, _ObjT]],
    key_factory: Callable[[str, str], _KeyT],
) -> dict[_KeyT, _ObjT]:
    """
    Flatten every schema's objects (as picked by `select`) into one (schema, name) -> object
    map, keyed by `key_factory(schema_name, name)` (RelationKey for views/matviews,
    CompositeTypeKey for composite types). Global flattening is needed for object kinds whose
    create/drop order crosses schemas, so the whole set orders as one.
    """
    objects: dict[_KeyT, _ObjT] = {}
    for schema_name, schema in db_introspection_result.schema_by_name.items():
        for name, obj in select(schema).items():
            objects[key_factory(schema_name, name)] = obj
    return objects


def dependents_closure(seeds: set[RelationKey], edges: Mapping[RelationKey, set[RelationKey]]) -> set[RelationKey]:
    """
    Every relation that transitively reads any relation in `seeds`, plus the seeds themselves.
    Used for the recreate cascade: recreating a relation forces every relation that reads it
    (directly or through a chain) to be recreated too. Edges are dependent -> the set it reads.
    """
    reverse: dict[RelationKey, set[RelationKey]] = {}
    for node, node_deps in edges.items():
        for dep in node_deps:
            reverse.setdefault(dep, set()).add(node)

    result = set(seeds)
    stack = list(seeds)
    while stack:
        current = stack.pop()
        for dependent in reverse.get(current, set()):
            if dependent not in result:
                result.add(dependent)
                stack.append(dependent)
    return result


def recreated_view_keys(
    source: DbIntrospectionResult, target: DbIntrospectionResult, retyped_column_readers: set[RelationKey]
) -> set[RelationKey]:
    """
    Plain views the migration drops and recreates: a changed definition or option set (CREATE OR
    REPLACE VIEW cannot reshape columns, and options live outside the definition), or reading a
    table column whose type changes -- plus every view that transitively reads one of those
    (Postgres refuses to drop a view another view still reads).

    Shared by the view diff and the matview recreate cascade: a matview reading a recreated view
    must itself be recreated. Read it through context.recreated_view_keys, which caches it for the
    diff scope.
    """
    src_views = collect_relations(source, lambda schema: schema.view_by_name, RelationKey)
    dst_views = collect_relations(target, lambda schema: schema.view_by_name, RelationKey)
    shared = src_views.keys() & dst_views.keys()
    changed = {
        key
        for key in shared
        if src_views[key].definition != dst_views[key].definition or src_views[key].options != dst_views[key].options
    }
    return dependents_closure(changed | retyped_column_readers, source.view_dependencies) & shared


def recreated_matview_keys(
    source: DbIntrospectionResult,
    target: DbIntrospectionResult,
    retyped_column_readers: set[RelationKey],
    recreated_views: set[RelationKey],
) -> set[RelationKey]:
    """
    Materialized views present on both sides that the migration drops and recreates: the
    definition changed (there is no CREATE OR REPLACE MATERIALIZED VIEW), the matview reads a
    table column whose type changes (Postgres refuses ALTER COLUMN ... TYPE while the column is
    read, and the type change leaves the definition unchanged, so only the column edge catches
    it), or the matview reads a view or matview that is itself recreated -- propagated to a fixed
    point over matview-on-matview edges.

    The single source of truth for the recreate decision, consumed by both the matview diff
    (which drops and recreates) and the matview-index differ (a recreated matview loses its
    indexes, so every target index is created fresh). A matview present on only one side is a
    plain create or drop, not a recreate, and is absent here. Read it through
    context.recreated_matview_keys, which caches it for the diff scope.
    """
    src_matviews = collect_relations(source, lambda schema: schema.materialized_view_by_name, RelationKey)
    dst_matviews = collect_relations(target, lambda schema: schema.materialized_view_by_name, RelationKey)
    both = src_matviews.keys() & dst_matviews.keys()

    edges = source.matview_dependencies

    # Seed: changed definition, retyped-column reader, or a matview reading a recreated plain view
    # (edges to plain views intersect recreated_views; edges to matviews intersect below).
    recreated = {
        key
        for key in both
        if src_matviews[key].definition != dst_matviews[key].definition
        or key in retyped_column_readers
        or edges.get(key, set()) & recreated_views
    }
    # Propagate to a fixed point over matview-on-matview edges: a matview reading a recreated
    # matview must itself be recreated.
    while added := {key for key in both if key not in recreated and edges.get(key, set()) & recreated}:
        recreated |= added
    return recreated
