from collections.abc import Iterator

from pgmig._diff._core import Context, Phase, Statement, _diff_comments, _iter_schema_pairs
from pgmig._models import View
from pgmig._sql import comment_on, qualified


def _view_comment_statements(
    schema_name: str, src: dict[str, View], dst: dict[str, View], recreated: set[str]
) -> list[str]:
    """
    Emit COMMENT ON VIEW for target views whose comment differs from source (a recreated
    view always re-emits, since the drop-and-recreate reset its comment).
    """
    return _diff_comments(
        src,
        dst,
        render=lambda name, view: comment_on("VIEW", qualified(schema_name, name), view.comment),
        recreated=recreated,
    )


def generate(ctx: Context) -> Iterator[Statement]:
    """
    Generate the migration SQL of views. Creates are phased after the tables and functions
    a view reads from exist; drops run before those objects are dropped. A changed
    definition is a drop-and-recreate (CREATE OR REPLACE VIEW cannot reshape columns).
    """
    for schema_name, src_schema, dst_schema in _iter_schema_pairs(ctx.source, ctx.target):
        src_views = src_schema.view_by_name if src_schema else {}
        dst_views = dst_schema.view_by_name if dst_schema else {}

        # Views recreated (definition changed): the drop resets the comment, so it must
        # be re-emitted even when unchanged.
        recreated: set[str] = set()
        for name in sorted(src_views.keys() | dst_views.keys()):
            src_view = src_views.get(name)
            dst_view = dst_views.get(name)
            qualified_name = qualified(schema_name, name)

            # Present in target only: create it.
            if src_view is None:
                yield Statement(Phase.VIEW_CREATE, f"CREATE VIEW {qualified_name} AS {dst_views[name].definition};")
            # Present in source only: drop it.
            elif dst_view is None:
                yield Statement(Phase.VIEW_DROP, f"DROP VIEW {qualified_name};")
            # Present in both with a changed definition: drop and recreate.
            elif src_view.definition != dst_view.definition:
                yield Statement(Phase.VIEW_DROP, f"DROP VIEW {qualified_name};")
                yield Statement(Phase.VIEW_CREATE, f"CREATE VIEW {qualified_name} AS {dst_view.definition};")
                recreated.add(name)

        # Sync comments for target views, after the views they annotate exist.
        for sql in _view_comment_statements(schema_name, src_views, dst_views, recreated):
            yield Statement(Phase.VIEW_CREATE, sql)
