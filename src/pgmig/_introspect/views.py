from collections.abc import Callable
from typing import Any, TypeVar

import psycopg
from pydantic import BaseModel

from pgmig._introspect._core import _run_query
from pgmig._models import DbInfo, Schema, View

_T = TypeVar("_T")


class _ViewRow(BaseModel):
    schema_name: str
    view_name: str
    view_definition: str
    view_comment: str | None


def _load_views(
    conn: psycopg.Connection[Any],
    db_info: DbInfo,
    query_file: str,
    select_target: Callable[[Schema], dict[str, _T]],
    build: Callable[[str, str, str | None], _T],
) -> None:
    """
    Shared body for the view and materialized-view loaders. Their queries are identical but
    for the relkind, and their loaders differ only in which schema mapping receives the
    result and which model is built; both differences are supplied by the caller so the
    parsing lives in one place. `select_target` picks the schema's view/matview mapping;
    `build` turns (name, definition, comment) into the object to store.
    """
    for row in _run_query(conn, query_file, _ViewRow):
        # pg_get_viewdef renders the SELECT with surrounding whitespace and a trailing
        # semicolon; strip both so the stored definition is what follows "AS".
        definition = row.view_definition.strip().rstrip(";").strip()
        select_target(db_info.schema_by_name[row.schema_name])[row.view_name] = build(
            row.view_name, definition, row.view_comment
        )


def load(conn: psycopg.Connection[Any], db_info: DbInfo) -> None:
    """
    Views (user views only; extension-owned ones are excluded).
    """
    _load_views(
        conn,
        db_info,
        "views.sql",
        lambda schema: schema.view_by_name,
        lambda name, definition, comment: View(name=name, definition=definition, comment=comment),
    )
