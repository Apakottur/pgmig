from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol, TypeVar

from pgmig._diff._context import context
from pgmig._models import ColumnKey, Schema, Table
from pgmig._sql import comment_on, ident, qualified

_Renamable = TypeVar("_Renamable")
_ObjT = TypeVar("_ObjT")


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
    """
    statements: list[str] = []
    for name in sorted(dst):
        if name in recreated:
            src_comment = None
        else:
            src_obj = src.get(name)
            src_comment = src_obj.comment if src_obj is not None else None
        if src_comment != dst[name].comment:
            statements.append(render(name, dst[name]))
    return statements


def diff_comment_statements(
    schema_name: str,
    src: Mapping[str, _CommentedT],
    dst: Mapping[str, _CommentedT],
    *,
    kind: str,
    recreated: frozenset[str] | set[str] = frozenset(),
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
    )


def diff_child_comment_statements(
    schema_name: str,
    table_name: str,
    src: Mapping[str, _CommentedT],
    dst: Mapping[str, _CommentedT],
    *,
    kind: str,
    recreated: frozenset[str] | set[str] = frozenset(),
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
    )


class Phase(Enum):
    """
    Global ordering bucket for a migration statement. Members are declared in
    execution order (priority); statements are grouped by phase and emitted by
    iterating the enum, so a statement's position is decided by its dependency
    phase, not by generator call order.
    """

    FOREIGN_KEY_DROP = auto()  # Before a referenced table / key is dropped.
    VIEW_DROP = auto()  # Before the tables/functions a view/matview reads from are dropped.
    TRIGGER_DROP = auto()  # Before the function a trigger calls is dropped.
    FUNCTION_DROP = auto()  # Before tables a routine body may depend on.
    SCHEMA_CREATE = auto()
    EXTENSION_CREATE = auto()  # Before tables/types that may use what the extension provides.
    TYPE_CREATE = auto()  # Before tables (a column may be of the type) and its ADD VALUE alters.
    SEQUENCE_CREATE = auto()  # Before tables (a column default may reference a sequence).
    TABLE = auto()
    INDEX = auto()
    CONSTRAINT = auto()
    COLUMN_DROP_NOT_NULL = auto()  # After a covering primary key is dropped in CONSTRAINT.
    FUNCTION_CREATE = auto()  # After tables so routine bodies can reference them.
    VIEW_CREATE = auto()  # After the tables/functions a view/matview reads from exist.
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


def retyped_column_refs() -> set[ColumnKey]:
    """
    Columns of tables present on both sides whose type changes between source and target.
    Postgres refuses ALTER COLUMN ... TYPE while a view reads the column, and -- unlike a
    dropped column -- a type change leaves the reading view's definition text unchanged, so
    the view-definition recreate path never catches it. The view diff intersects these with
    its view-on-column edges to decide which views to drop and recreate around the change.

    Source-side identity (a column read by a source view exists in the source). A serial
    change keeps the integer `type`, so it does not surface here; that is intentional -- a
    serial change is unsupported and raised by the table diff before applying.
    """
    refs: set[ColumnKey] = set()
    for schema_name, table_name, src_table, dst_table in ctx_iter_table_pairs():
        if src_table is None or dst_table is None:
            continue
        dst_columns = {column.name: column for column in dst_table.columns}
        for src_column in src_table.columns:
            dst_column = dst_columns.get(src_column.name)
            if dst_column is not None and src_column.type != dst_column.type:
                refs.add(ColumnKey(schema_name, table_name, src_column.name))
    return refs


def diff_renamable(
    src: dict[str, _Renamable],
    dst: dict[str, _Renamable],
    *,
    key: Callable[[_Renamable], str],
    render_drop: Callable[[str], str],
    render_rename: Callable[[str, str], str],
    render_create: Callable[[str, _Renamable], str],
) -> tuple[list[str], list[str], list[str], set[str]]:
    """
    Diff two name->object mappings whose objects carry a name-independent `key`,
    detecting renames (same key, different name).

    Returns:
        A 4-tuple (drops, renames, creates, recreated) of rendered SQL statements plus
        the set of names that were both dropped and recreated (same name, changed
        definition). A shared name is a no-op when the keys match; otherwise objects
        are dropped, renamed (same key across a name change), or created. `recreated`
        lets the comment diff force a re-emit, since a recreate resets the comment.
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
    for shared_key in sorted(src_by_key.keys() & dst_by_key.keys()):
        src_names = sorted(src_by_key[shared_key])
        dst_names = sorted(dst_by_key[shared_key])
        # A shared key with an identical name was removed as a no-op above, so every
        # pair here is a genuine rename. Counts may differ, so pair up to the shorter.
        for old_name, new_name in zip(src_names, dst_names, strict=False):
            renames.append(render_rename(old_name, new_name))
            del src[old_name]
            del dst[new_name]

    # After the no-op and rename passes, a name still in both sides is dropped and
    # recreated (same name, changed definition).
    recreated = src.keys() & dst.keys()
    drops = [render_drop(name) for name in sorted(src.keys())]
    creates = [render_create(name, dst[name]) for name in sorted(dst.keys())]
    return drops, renames, creates, recreated
