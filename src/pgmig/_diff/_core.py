from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol, TypeVar

from pgmig._models import DbInfo, Schema, Table

_Renamable = TypeVar("_Renamable")


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


class Phase(Enum):
    """
    Global ordering bucket for a migration statement. Members are declared in
    execution order (priority); statements are grouped by phase and emitted by
    iterating the enum, so a statement's position is decided by its dependency
    phase, not by generator call order.
    """

    FOREIGN_KEY_DROP = auto()  # Before a referenced table / key is dropped.
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


@dataclass(frozen=True)
class Options:
    """
    Output options that tune how statements are rendered, threaded uniformly to every
    generator (most ignore it; today only index generation reads a field).

    index_concurrently: emit CREATE/DROP INDEX (including CREATE UNIQUE INDEX) with
        CONCURRENTLY so index maintenance does not take a blocking lock. The resulting
        statements cannot run inside a transaction block -- the caller must apply them
        outside BEGIN/COMMIT.
    """

    index_concurrently: bool = False


class Generator(Protocol):
    """
    The shared shape of every object-kind generator: keyword-only source, target and
    options, yielding phase-tagged statements. Annotating the registry with this enforces
    one uniform signature (names included) across all generators.
    """

    def __call__(self, *, source: DbInfo, target: DbInfo, options: Options) -> Iterator[Statement]: ...


def _iter_schema_pairs(source: DbInfo, target: DbInfo) -> Iterator[tuple[str, Schema | None, Schema | None]]:
    """
    Yield (schema_name, source_schema, target_schema) for every schema across both
    databases, sorted by name. Either schema is None when absent on that side.
    """
    for schema_name in sorted(source.schema_by_name.keys() | target.schema_by_name.keys()):
        yield schema_name, source.schema_by_name.get(schema_name), target.schema_by_name.get(schema_name)


def _iter_table_pairs(source: DbInfo, target: DbInfo) -> Iterator[tuple[str, str, Table | None, Table | None]]:
    """
    Yield (schema_name, table_name, source_table, target_table) for every table across
    both databases, sorted by schema then table. Either table is None when absent on
    that side.
    """
    for schema_name, src_schema, dst_schema in _iter_schema_pairs(source, target):
        src_tables = src_schema.table_by_name if src_schema else {}
        dst_tables = dst_schema.table_by_name if dst_schema else {}
        for table_name in sorted(src_tables.keys() | dst_tables.keys()):
            yield schema_name, table_name, src_tables.get(table_name), dst_tables.get(table_name)


def _diff_renamable(
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
