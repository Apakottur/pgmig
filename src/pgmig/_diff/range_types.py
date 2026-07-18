from collections.abc import Iterator

from pgmig._diff._core import Phase, Statement, ctx_iter_object_pairs, diff_comment_statements
from pgmig._models import RangeType
from pgmig._sql import qualified


def _create(qualified_name: str, range_type: RangeType) -> str:
    """
    Render CREATE TYPE ... AS RANGE, emitting only the clauses the range actually carries
    (the loader leaves the rest None, so an omitted clause takes Postgres's default).
    """
    clauses = [f"SUBTYPE = {range_type.subtype}"]
    if range_type.subtype_opclass is not None:
        clauses.append(f"SUBTYPE_OPCLASS = {range_type.subtype_opclass}")
    if range_type.collation is not None:
        clauses.append(f"COLLATION = {range_type.collation}")
    if range_type.subtype_diff is not None:
        clauses.append(f"SUBTYPE_DIFF = {range_type.subtype_diff}")
    return f"CREATE TYPE {qualified_name} AS RANGE ({', '.join(clauses)});"


def _properties(range_type: RangeType) -> tuple[str | None, ...]:
    """
    The name-independent properties that define a range type; two ranges with equal
    properties are identical and need no migration.
    """
    return (
        range_type.subtype,
        range_type.subtype_opclass,
        range_type.collation,
        range_type.subtype_diff,
    )


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of range types (create, drop, recreate). Creates are phased
    before tables (a column may be of the type); a standalone drop runs after.

    A range type has no ALTER form for its properties, so a property change is a drop +
    recreate. Both statements go in Phase.TYPE_CREATE (drop first, adjacent): the drop phase
    runs after tables, so splitting the pair across phases would emit the create before the
    drop and fail. Postgres refuses the DROP if a column still uses the type, so a change to
    an in-use range surfaces as an error at apply time -- an accepted first-cut limitation.
    """
    for schema_name, src_ranges, dst_ranges, pairs in ctx_iter_object_pairs(lambda schema: schema.range_type_by_name):
        recreated: set[str] = set()
        for name, src_range, dst_range in pairs:
            qualified_name = qualified(schema_name, name)

            # Present in target only: create it.
            if src_range is None:
                yield Statement(Phase.TYPE_CREATE, _create(qualified_name, dst_ranges[name]))
            # Present in source only: drop it (after the tables whose columns used it).
            elif dst_range is None:
                yield Statement(Phase.TYPE_DROP, f"DROP TYPE {qualified_name};")
            # Present in both with differing properties: drop and recreate in place.
            elif _properties(src_range) != _properties(dst_range):
                yield Statement(Phase.TYPE_CREATE, f"DROP TYPE {qualified_name};")
                yield Statement(Phase.TYPE_CREATE, _create(qualified_name, dst_ranges[name]))
                recreated.add(name)

        # Sync comments for target ranges, after the types they annotate exist. A recreated
        # range lost its comment in the drop, so its target comment is re-emitted even when
        # unchanged (mirrors the index/constraint recreate-comment handling).
        for sql in diff_comment_statements(schema_name, src_ranges, dst_ranges, kind="TYPE", recreated=recreated):
            yield Statement(Phase.TYPE_CREATE, sql)
