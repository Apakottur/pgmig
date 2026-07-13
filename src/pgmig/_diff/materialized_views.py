from collections.abc import Iterator

from pgmig._diff._core import Phase, Statement, _diff_comments, ctx_iter_schema_pairs
from pgmig._models import MaterializedView
from pgmig._sql import comment_on, qualified


def _materialized_view_comment_statements(
    schema_name: str, src: dict[str, MaterializedView], dst: dict[str, MaterializedView], recreated: set[str]
) -> list[str]:
    """
    Emit COMMENT ON MATERIALIZED VIEW for target matviews whose comment differs from source
    (a recreated matview always re-emits, since the drop-and-recreate reset its comment).
    """
    return _diff_comments(
        src,
        dst,
        render=lambda name, view: comment_on("MATERIALIZED VIEW", qualified(schema_name, name), view.comment),
        recreated=recreated,
    )


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of materialized views. Creates are phased after the tables and
    functions a matview reads from exist; drops run before those objects are dropped. A changed
    definition is a drop-and-recreate (there is no CREATE OR REPLACE MATERIALIZED VIEW). Creates
    use WITH NO DATA: the matview is created unpopulated and the user runs REFRESH themselves.
    """
    for schema_name, src_schema, dst_schema in ctx_iter_schema_pairs():
        src_views = src_schema.materialized_view_by_name if src_schema else {}
        dst_views = dst_schema.materialized_view_by_name if dst_schema else {}

        # Matviews recreated (definition changed): the drop resets the comment, so it must
        # be re-emitted even when unchanged.
        recreated: set[str] = set()
        for name in sorted(src_views.keys() | dst_views.keys()):
            src_view = src_views.get(name)
            dst_view = dst_views.get(name)
            qualified_name = qualified(schema_name, name)

            # Present in target only: create it.
            if src_view is None:
                yield Statement(
                    Phase.VIEW_CREATE,
                    f"CREATE MATERIALIZED VIEW {qualified_name} AS {dst_views[name].definition} WITH NO DATA;",
                )
            # Present in source only: drop it.
            elif dst_view is None:
                yield Statement(Phase.VIEW_DROP, f"DROP MATERIALIZED VIEW {qualified_name};")
            # Present in both with a changed definition: drop and recreate.
            elif src_view.definition != dst_view.definition:
                yield Statement(Phase.VIEW_DROP, f"DROP MATERIALIZED VIEW {qualified_name};")
                yield Statement(
                    Phase.VIEW_CREATE,
                    f"CREATE MATERIALIZED VIEW {qualified_name} AS {dst_view.definition} WITH NO DATA;",
                )
                recreated.add(name)

        # Sync comments for target matviews, after the matviews they annotate exist.
        for sql in _materialized_view_comment_statements(schema_name, src_views, dst_views, recreated):
            yield Statement(Phase.VIEW_CREATE, sql)
