from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from pgmig._diff._context import context
from pgmig._diff._core import (
    Phase,
    Statement,
    ctx_iter_object_pairs,
    diff_comment_statements,
    owner_statements,
    topological_drop_order,
    topological_sort,
)
from pgmig._diff._relations import collect_relations
from pgmig._keys import RelationKey
from pgmig._models import DbIntrospectionResult, Schema
from pgmig._sql import qualified


class _ViewLike(Protocol):
    """
    Any view-like relation: owned and optionally commented. Declared as read-only properties so
    plain (frozen) dataclass attributes satisfy it.
    """

    @property
    def comment(self) -> str | None: ...

    @property
    def owner(self) -> str: ...


_ViewT = TypeVar("_ViewT", bound=_ViewLike)


@dataclass(frozen=True)
class ViewKind(Generic[_ViewT]):
    """
    The per-kind differences between the view and the materialized view diffs.
    """

    keyword: str  # DROP/CREATE/ALTER object keyword: VIEW or MATERIALIZED VIEW.
    select: Callable[[Schema], Mapping[str, _ViewT]]  # Picks the kind's name->object map off a schema.
    dependencies: Callable[[DbIntrospectionResult], Mapping[RelationKey, set[RelationKey]]]
    recreated: Callable[[], set[RelationKey]]  # Reads the cached recreate set off the diff context.
    create_sql: Callable[[str, _ViewT], str]  # The CREATE statement, given the qualified name.
    drop_phase: Phase
    create_phase: Phase


def generate_view_kind(kind: ViewKind[_ViewT]) -> Iterator[Statement]:
    """
    Generate the migration SQL of one view kind: drops dependent-first over the source graph,
    creates dependency-first over the target graph, then ownership and comments.
    """
    source, target = context().source, context().target
    src_objects = collect_relations(source, kind.select, RelationKey)
    dst_objects = collect_relations(target, kind.select, RelationKey)

    recreate = kind.recreated()
    drop_only = src_objects.keys() - dst_objects.keys()
    create_only = dst_objects.keys() - src_objects.keys()

    # Drops: dependent-first over the source graph.
    drops = drop_only | recreate
    for key in topological_drop_order(drops, kind.dependencies(source)):
        yield Statement(kind.drop_phase, f"DROP {kind.keyword} {qualified(key.schema, key.name)};")

    # Creates: dependency-first over the target graph.
    creates = create_only | recreate
    for key in topological_sort(creates, kind.dependencies(target)):
        yield Statement(kind.create_phase, kind.create_sql(qualified(key.schema, key.name), dst_objects[key]))

    # Ownership, for an object present unchanged on both sides. A recreated one is skipped: its
    # rebuilt instance is owned by the migration runner and reconciles on a later run, like a
    # create.
    for key in sorted(src_objects.keys() & dst_objects.keys(), key=lambda k: (k.schema, k.name)):
        if key in recreate:
            continue
        for sql in owner_statements(
            kind.keyword, qualified(key.schema, key.name), src_objects[key].owner, dst_objects[key].owner
        ):
            yield Statement(kind.create_phase, sql)

    # Comments, after the objects they annotate exist. A recreated object re-emits its comment
    # (the drop reset it), so pass the recreated names per schema.
    for schema_name, src_schema_objects, dst_schema_objects, _pairs in ctx_iter_object_pairs(kind.select):
        recreated_names = {key.name for key in recreate if key.schema == schema_name}
        for sql in diff_comment_statements(
            schema_name, src_schema_objects, dst_schema_objects, kind=kind.keyword, recreated=recreated_names
        ):
            yield Statement(kind.create_phase, sql)
