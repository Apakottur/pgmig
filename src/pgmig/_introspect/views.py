from collections.abc import Callable
from typing import TypeVar

from pgmig._introspect._context import context
from pgmig._introspect._core import _QueryRow, run_introspection_query
from pgmig._models import Schema, View

_T = TypeVar("_T")


class _ViewRow(_QueryRow):
    schema_name: str
    view_name: str
    view_definition: str
    view_comment: str | None
    view_options: list[str] | None  # pg_class.reloptions; NULL when the view has none


async def _load_views(
    query_file: str,
    select_target: Callable[[Schema], dict[str, _T]],
    build: Callable[[str, str, str | None, tuple[str, ...]], _T],
) -> None:
    """
    Shared body for the view and materialized-view loaders. Their queries are identical but
    for the relkind, and their loaders differ only in which schema mapping receives the
    result and which model is built; both differences are supplied by the caller so the
    parsing lives in one place. `select_target` picks the schema's view/matview mapping;
    `build` turns (name, definition, comment, options) into the object to store.
    """
    for row in await run_introspection_query(query_file, _ViewRow):
        # pg_get_viewdef renders the SELECT with surrounding whitespace and a trailing
        # semicolon; strip both so the stored definition is what follows "AS".
        definition = row.view_definition.strip().rstrip(";").strip()
        # reloptions come back in creation order; sort so comparison is order-independent.
        options = tuple(sorted(row.view_options or []))
        select_target(context.db_introspection_result.schema_by_name[row.schema_name])[row.view_name] = build(
            row.view_name, definition, row.view_comment, options
        )


async def load() -> None:
    """
    Views (user views only; extension-owned ones are excluded).
    """
    await _load_views(
        "views.sql",
        lambda schema: schema.view_by_name,
        lambda name, definition, comment, options: View(
            name=name, definition=definition, comment=comment, options=options
        ),
    )
