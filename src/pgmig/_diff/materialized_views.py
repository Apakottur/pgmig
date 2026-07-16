from collections.abc import Iterator

from pgmig._diff._core import Phase, Statement, ctx_iter_object_pairs, diff_comment_statements, recreated_matview_keys
from pgmig._keys import ViewKey
from pgmig._sql import qualified


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of materialized views. Creates are phased after the tables and
    functions a matview reads from exist; drops run before those objects are dropped. A changed
    definition is a drop-and-recreate (there is no CREATE OR REPLACE MATERIALIZED VIEW). Creates
    use WITH NO DATA: the matview is created unpopulated and the user runs REFRESH themselves.

    A matview reading a table column whose type changes is also dropped-and-recreated: Postgres
    refuses ALTER COLUMN ... TYPE while a matview reads the column, and the type change leaves
    the matview definition unchanged, so only the matview-on-column edge catches it. The drop
    lands in VIEW_DROP (before the TABLE-phase change) and the recreate in VIEW_CREATE (after).
    Matviews cannot depend on other managed views/matviews (that pairing is refused upstream),
    so each matview is independent -- no transitive cascade is needed.
    """
    # Matviews the migration drops and recreates (definition changed, or reading a retyped
    # column). Shared with the matview-index differ so both agree on which matviews are recreated.
    recreated_keys = recreated_matview_keys()

    for schema_name, src_views, dst_views, pairs in ctx_iter_object_pairs(
        lambda schema: schema.materialized_view_by_name
    ):
        # Matviews recreated (definition changed, or reading a retyped column): the drop resets
        # the comment, so it must be re-emitted even when unchanged.
        recreated: set[str] = set()
        for name, src_view, dst_view in pairs:
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
            # Present in both and recreated (changed definition, or reading a retyped column):
            # drop and recreate. A type change leaves the definition unchanged, so the column
            # edge is the only signal in that case.
            elif ViewKey(schema_name, name) in recreated_keys:
                yield Statement(Phase.VIEW_DROP, f"DROP MATERIALIZED VIEW {qualified_name};")
                yield Statement(
                    Phase.VIEW_CREATE,
                    f"CREATE MATERIALIZED VIEW {qualified_name} AS {dst_view.definition} WITH NO DATA;",
                )
                recreated.add(name)

        # Sync comments for target matviews, after the matviews they annotate exist.
        for sql in diff_comment_statements(
            schema_name, src_views, dst_views, kind="MATERIALIZED VIEW", recreated=recreated
        ):
            yield Statement(Phase.VIEW_CREATE, sql)
