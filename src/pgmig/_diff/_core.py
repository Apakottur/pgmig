import heapq
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, NamedTuple, Protocol, TypeVar

from pgmig._diff._context import context
from pgmig._keys import RelationKey
from pgmig._models import DbIntrospectionResult, Schema, Table
from pgmig._sql import comment_on, ident, qualified

if TYPE_CHECKING:
    from _typeshed import SupportsRichComparison

_Renamable = TypeVar("_Renamable")
_ObjT = TypeVar("_ObjT")
_KeyT = TypeVar("_KeyT")
_SortableT = TypeVar("_SortableT", bound="SupportsRichComparison")


def topological_sort(nodes: set[_SortableT], edges: Mapping[_SortableT, set[_SortableT]]) -> list[_SortableT]:
    """
    Order `nodes` dependencies-first via Kahn's algorithm: a node appears after every node
    it points to in `edges` that is also in `nodes` (edges leaving the set are ignored).
    Ties break by sorted node, so the output is deterministic regardless of set iteration
    order.

    A cycle raises rather than silently dropping the cyclic nodes: cyclic nodes never reach
    zero remaining dependencies, so a plain Kahn's loop would just omit them -- and a caller
    that reverses this order to emit DROPs would then produce a non-converging diff with no
    error. Postgres forbids cycles among views and among SQL-body routines, so this guards a
    can't-happen case.
    """
    deps = {node: {dep for dep in edges.get(node, set()) if dep in nodes} for node in nodes}
    dependents: dict[_SortableT, set[_SortableT]] = {node: set() for node in nodes}
    for node, node_deps in deps.items():
        for dep in node_deps:
            dependents[dep].add(node)

    # A min-heap keeps the ready set ordered smallest-first: heappop yields the next node in
    # sorted order (the deterministic tie-break) in O(log n), and a freed dependent is pushed
    # in O(log n) -- versus pop(0) + a full re-sort every iteration.
    ready = [node for node, node_deps in deps.items() if not node_deps]
    heapq.heapify(ready)
    order: list[_SortableT] = []
    while ready:
        node = heapq.heappop(ready)
        order.append(node)
        for dependent in dependents[node]:
            deps[dependent].discard(node)
            if not deps[dependent]:
                heapq.heappush(ready, dependent)

    if len(order) != len(nodes):
        cyclic = sorted(nodes - set(order))
        raise AssertionError(f"dependency cycle detected among: {', '.join(repr(node) for node in cyclic)}")
    return order


def topological_drop_order(nodes: set[_SortableT], edges: Mapping[_SortableT, set[_SortableT]]) -> list[_SortableT]:
    """
    Order `nodes` dependents-first for dropping: a node appears before every node it points to
    in `edges`, so an object is dropped before the objects it depends on (Postgres refuses to
    drop something another kept object still references).

    The reverse of `topological_sort`'s dependency-first order over the same forward `edges`
    (object -> the set it depends on). Every drop path shares this idiom.
    """
    return list(reversed(topological_sort(nodes, edges)))


class _Commented(Protocol):
    """
    Any object carrying an optional comment. Declared as a read-only property so plain
    (frozen) dataclass attributes satisfy it.
    """

    @property
    def comment(self) -> str | None: ...


_CommentedT = TypeVar("_CommentedT", bound=_Commented)


def _diff_comments(
    src: Mapping[str, _CommentedT],
    dst: Mapping[str, _CommentedT],
    *,
    render: Callable[[str, _CommentedT], str],
    recreated: frozenset[str] | set[str] = frozenset(),
    renamed_from: Mapping[str, str] | None = None,
) -> list[str]:
    """
    Diff comments across two name->object mappings whose objects carry `.comment`.

    Returns a rendered COMMENT ON statement, in sorted-name order, for every target
    object whose comment differs from source (an absent source object counts as no
    comment). The sorted iteration makes the output deterministic regardless of the
    introspection row order, and gathering the pattern here removes the hand-copied
    "(src.comment if src else None) != dst.comment" checks scattered per object kind.

    A name in `recreated` was dropped and recreated by the migration, which resets its
    comment to NULL. Its source comment is therefore treated as None so the target
    comment is always re-emitted; otherwise an unchanged comment would be silently lost
    and leave a residual diff.

    `renamed_from` maps a target (new) name to its source (old) name for objects renamed
    this run. A rename preserves the comment, so the source comment is resolved through the
    old name; without this the lookup by new name misses, the source comment reads as None,
    and a `COMMENT ... IS NULL` is never emitted when the target dropped the comment -- the
    renamed object keeps the stale comment and the migration does not converge.
    """
    renamed_from = renamed_from or {}
    statements: list[str] = []
    for name in sorted(dst):
        if name in recreated:
            src_comment = None
        else:
            src_obj = src.get(renamed_from.get(name, name))
            src_comment = src_obj.comment if src_obj is not None else None
        if src_comment != dst[name].comment:
            statements.append(render(name, dst[name]))
    return statements


def diff_single_comment(
    src_obj: _CommentedT | None,
    dst_obj: _CommentedT,
    *,
    render: Callable[[_CommentedT], str],
) -> list[str]:
    """
    Single-object counterpart to _diff_comments: render a COMMENT ON for `dst_obj` when
    its comment differs from `src_obj` (an absent source object counts as no comment),
    else nothing. Wraps the pair in a one-entry mapping and defers to _diff_comments so
    the "absent source = None" rule lives in exactly one place, rather than being
    hand-copied as `(src.comment if src else None) != dst.comment` per object kind.
    """
    return _diff_comments(
        {} if src_obj is None else {"": src_obj},
        {"": dst_obj},
        render=lambda _name, obj: render(obj),
    )


def diff_comment_statements(
    schema_name: str,
    src: Mapping[str, _CommentedT],
    dst: Mapping[str, _CommentedT],
    *,
    kind: str,
    recreated: frozenset[str] | set[str] = frozenset(),
    renamed_from: Mapping[str, str] | None = None,
) -> list[str]:
    """
    COMMENT ON <kind> for every target object (identified by its schema-qualified name)
    whose comment differs from source. The render shared by every schema-qualified object
    kind (types, domains, sequences, indexes, views, ...), gathered here so the per-kind
    generators name their `kind` rather than each restating the _diff_comments call.
    """
    return _diff_comments(
        src,
        dst,
        render=lambda name, obj: comment_on(kind, qualified(schema_name, name), obj.comment),
        recreated=recreated,
        renamed_from=renamed_from,
    )


def diff_child_comment_statements(
    schema_name: str,
    table_name: str,
    src: Mapping[str, _CommentedT],
    dst: Mapping[str, _CommentedT],
    *,
    kind: str,
    recreated: frozenset[str] | set[str] = frozenset(),
    renamed_from: Mapping[str, str] | None = None,
) -> list[str]:
    """
    COMMENT ON <kind> for a table-owned object addressed as `<name> ON <table>`
    (constraints, triggers) whose comment differs from source.
    """
    table = qualified(schema_name, table_name)
    return _diff_comments(
        src,
        dst,
        render=lambda name, obj: comment_on(kind, f"{ident(name)} ON {table}", obj.comment),
        recreated=recreated,
        renamed_from=renamed_from,
    )


class Phase(Enum):
    """
    Global ordering bucket for a migration statement. Members are declared in
    execution order (priority); statements are grouped by phase and emitted by
    iterating the enum, so a statement's position is decided by its dependency
    phase, not by generator call order.
    """

    FOREIGN_KEY_DROP = auto()  # Before a referenced table / key is dropped.
    MATVIEW_DROP = auto()  # Before the views/tables/functions a matview reads are dropped (incl. VIEW_DROP).
    VIEW_DROP = auto()  # Before the tables/functions a view reads from are dropped.
    TRIGGER_DROP = auto()  # Before the function a trigger calls is dropped.
    FUNCTION_DROP = auto()  # Before tables a routine body may depend on.
    SCHEMA_CREATE = auto()
    EXTENSION_CREATE = auto()  # Before tables/types that may use what the extension provides.
    TYPE_CREATE = auto()  # Before tables (a column may be of the type) and its ADD VALUE alters.
    SEQUENCE_CREATE = auto()  # Before tables (a column default may reference a sequence).
    TABLE = auto()
    SEQUENCE_OWNED_BY = auto()  # After tables: OWNED BY needs its target table/column to exist.
    INDEX = auto()
    CONSTRAINT = auto()
    COLUMN_DROP_NOT_NULL = auto()  # After a covering primary key is dropped in CONSTRAINT.
    REPLICA_IDENTITY = auto()  # After INDEX/CONSTRAINT: USING INDEX references an index by name.
    # After the column defaults / expression indexes / check constraints that depend on a routine.
    FUNCTION_DROP_LATE = auto()
    FUNCTION_CREATE = auto()  # After tables so routine bodies can reference them.
    VIEW_CREATE = auto()  # After the tables/functions a view reads from exist.
    MATVIEW_CREATE = auto()  # After VIEW_CREATE: a matview may read a plain view (and tables/functions).
    MATVIEW_INDEX_CREATE = auto()  # After the matview it indexes is created in MATVIEW_CREATE.
    TRIGGER_CREATE = auto()  # After the function it calls and its table exist.
    FOREIGN_KEY_ADD = auto()  # After referenced tables and their keys exist.
    SEQUENCE_DROP = auto()  # After tables that referenced the sequence are gone.
    TYPE_DROP = auto()  # After tables whose columns used the type are gone.
    EXTENSION_DROP = auto()  # After tables/types/functions the extension provided are gone.
    SCHEMA_DROP = auto()


@dataclass(frozen=True)
class Statement:
    """
    A migration SQL statement tagged with the phase that fixes its global position.
    """

    phase: Phase
    sql: str


class Generator(Protocol):
    """
    The shared shape of every object-kind generator: read the diff `context` and yield
    phase-tagged statements. Annotating the registry with this enforces one uniform
    signature across all generators.
    """

    def __call__(self) -> Iterator[Statement]: ...


def ctx_iter_schema_pairs() -> Iterator[tuple[str, Schema | None, Schema | None]]:
    """
    Yield (schema_name, source_schema, target_schema) for every schema across both
    databases, sorted by name. Either schema is None when absent on that side.
    """
    for schema_name in sorted(context.source.schema_by_name.keys() | context.target.schema_by_name.keys()):
        yield (
            schema_name,
            context.source.schema_by_name.get(schema_name),
            context.target.schema_by_name.get(schema_name),
        )


def ctx_iter_table_pairs() -> Iterator[tuple[str, str, Table | None, Table | None]]:
    """
    Yield (schema_name, table_name, source_table, target_table) for every table across
    both databases, sorted by schema then table. Either table is None when absent on
    that side.
    """
    for schema_name, src_schema, dst_schema in ctx_iter_schema_pairs():
        src_tables = src_schema.table_by_name if src_schema else {}
        dst_tables = dst_schema.table_by_name if dst_schema else {}
        for table_name in sorted(src_tables.keys() | dst_tables.keys()):
            yield schema_name, table_name, src_tables.get(table_name), dst_tables.get(table_name)


def ctx_iter_object_pairs(
    select: Callable[[Schema], Mapping[str, _ObjT]],
) -> Iterator[tuple[str, dict[str, _ObjT], dict[str, _ObjT], list[tuple[str, _ObjT | None, _ObjT | None]]]]:
    """
    For every schema across both databases (sorted), yield
    (schema_name, source_objects, target_objects, pairs), where `select` picks a
    name->object map off a Schema (empty when the schema is absent on that side) and
    `pairs` is the (name, source, target) triples over the union of names, sorted by name.

    Captures the create/drop/alter scaffold shared by the schema-scoped object generators:
    the body iterates `pairs`, while the object maps feed the trailing comment diff.
    """
    for schema_name, src_schema, dst_schema in ctx_iter_schema_pairs():
        src_objs: dict[str, _ObjT] = dict(select(src_schema)) if src_schema else {}
        dst_objs: dict[str, _ObjT] = dict(select(dst_schema)) if dst_schema else {}
        pairs = [(name, src_objs.get(name), dst_objs.get(name)) for name in sorted(src_objs.keys() | dst_objs.keys())]
        yield schema_name, src_objs, dst_objs, pairs


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


def recreated_view_keys() -> set[RelationKey]:
    """
    Plain views the migration drops and recreates: a changed definition or option set (CREATE OR
    REPLACE VIEW cannot reshape columns, and options live outside the definition), or reading a
    table column whose type changes -- plus every view that transitively reads one of those
    (Postgres refuses to drop a view another view still reads).

    Shared by the view diff and the matview recreate cascade: a matview reading a recreated view
    must itself be recreated.
    """
    source, target = context.source, context.target
    src_views = collect_relations(source, lambda schema: schema.view_by_name, RelationKey)
    dst_views = collect_relations(target, lambda schema: schema.view_by_name, RelationKey)
    shared = src_views.keys() & dst_views.keys()
    changed = {
        key
        for key in shared
        if src_views[key].definition != dst_views[key].definition or src_views[key].options != dst_views[key].options
    }
    return dependents_closure(changed | context.retyped_column_readers, source.view_dependencies) & shared


def recreated_matview_keys() -> set[RelationKey]:
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
    plain create or drop, not a recreate, and is absent here.
    """
    source, target = context.source, context.target
    src_matviews = collect_relations(source, lambda schema: schema.materialized_view_by_name, RelationKey)
    dst_matviews = collect_relations(target, lambda schema: schema.materialized_view_by_name, RelationKey)
    both = src_matviews.keys() & dst_matviews.keys()

    column_readers = context.retyped_column_readers
    recreated_views = recreated_view_keys()
    edges = source.matview_dependencies

    # Seed: changed definition, retyped-column reader, or a matview reading a recreated plain view
    # (edges to plain views intersect recreated_views; edges to matviews intersect below).
    recreated = {
        key
        for key in both
        if src_matviews[key].definition != dst_matviews[key].definition
        or key in column_readers
        or edges.get(key, set()) & recreated_views
    }
    # Propagate to a fixed point over matview-on-matview edges: a matview reading a recreated
    # matview must itself be recreated.
    while added := {key for key in both if key not in recreated and edges.get(key, set()) & recreated}:
        recreated |= added
    return recreated


class RenameDiff(NamedTuple):
    """
    Result of `diff_renamable`: the rendered SQL plus the two comment-diff inputs.

    `drops`/`renames`/`creates` are rendered SQL statements. `recreated` is the set of names
    whose object is freshly created and therefore starts without a comment -- a name dropped
    and recreated (same name, changed definition), or a create reusing a name a rename vacated
    this run. `renamed_from` maps each new name to its old name. The last two let the comment
    diff force a re-emit (a recreate resets the comment) and resolve a renamed object's source
    comment through its old name (a rename preserves the comment, so it must be cleared when
    the target has none).
    """

    drops: list[str]
    renames: list[str]
    creates: list[str]
    recreated: set[str]
    renamed_from: dict[str, str]


def diff_renamable(
    src: dict[str, _Renamable],
    dst: dict[str, _Renamable],
    *,
    key: Callable[[_Renamable], str],
    render_drop: Callable[[str], str],
    render_rename: Callable[[str, str], str],
    render_create: Callable[[str, _Renamable], str],
) -> RenameDiff:
    """
    Diff two name->object mappings whose objects carry a name-independent `key`,
    detecting renames (same key, different name), into a `RenameDiff`.

    A shared name is a no-op when the keys match; otherwise objects are dropped, renamed
    (same key across a name change), or created.
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
    renamed_from: dict[str, str] = {}
    for shared_key in sorted(src_by_key.keys() & dst_by_key.keys()):
        src_names = sorted(src_by_key[shared_key])
        dst_names = sorted(dst_by_key[shared_key])
        # A shared key with an identical name was removed as a no-op above, so every
        # pair here is a genuine rename. Counts may differ, so pair up to the shorter.
        for old_name, new_name in zip(src_names, dst_names, strict=False):
            renames.append(render_rename(old_name, new_name))
            renamed_from[new_name] = old_name
            del src[old_name]
            del dst[new_name]

    # After the no-op and rename passes, a name still in both sides is dropped and
    # recreated (same name, changed definition). A create whose name was vacated by a rename
    # this run (the old name of some rename) is a fresh object too: it carries no comment, but
    # the comment diff would resolve its name back to the renamed-away source object and find a
    # matching comment, suppressing the COMMENT and leaving a residual diff. Treat it as
    # recreated so its target comment is always emitted.
    recreated = (src.keys() & dst.keys()) | (dst.keys() & set(renamed_from.values()))
    drops = [render_drop(name) for name in sorted(src.keys())]
    creates = [render_create(name, dst[name]) for name in sorted(dst.keys())]
    return RenameDiff(drops, renames, creates, recreated, renamed_from)
