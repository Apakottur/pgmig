import re
from pathlib import Path
from typing import Any, Protocol, TypeVar, cast

import psycopg
from psycopg.rows import class_row
from pydantic import BaseModel
from typing_extensions import LiteralString

from pgmig._models import DbInfo

_RowT = TypeVar("_RowT", bound=BaseModel)

# Placeholder a query writes to exclude objects an extension owns: {{exclude_extension_owned:EXPR}},
# where EXPR is the candidate object's oid column (n.oid for its schema, c.oid for its owning table,
# t.oid/p.oid for the object itself). Expanded once here so the pg_depend leg lives in a single place
# rather than being hand-copied -- and re-verified -- into every query. Inner whitespace is tolerated
# because pgFormatter (the pg_format pre-commit hook) rewrites the token to `{{exclude... :EXPR }}`.
_EXTENSION_OWNED_PLACEHOLDER = re.compile(r"\{\{\s*exclude_extension_owned\s*:\s*([\w.]+)\s*\}\}")
_EXTENSION_OWNED_LEG = """AND NOT EXISTS (
        SELECT
            1
        FROM
            pg_depend d
        WHERE
            d.objid = {expr}
            AND d.deptype = 'e')"""


def _expand_query(query: str) -> str:
    """
    Expand every extension-ownership placeholder in a bundled query into the shared
    pg_depend NOT EXISTS leg, keyed by the placeholder's oid expression. Queries with no
    placeholder pass through unchanged.
    """
    return _EXTENSION_OWNED_PLACEHOLDER.sub(lambda match: _EXTENSION_OWNED_LEG.format(expr=match.group(1)), query)


def _run_query(conn: psycopg.Connection[Any], file_name: str, model: type[_RowT]) -> list[_RowT]:
    """
    Load a bundled SQL query from the queries directory, expand its shared fragments, run
    it, and parse each row into the given Pydantic model (by SELECT column alias).
    Validation happens at parse time, so a schema/type drift surfaces here rather than
    silently downstream.
    """
    file_path = Path(__file__).parent.joinpath("queries").joinpath(file_name)
    query = cast("LiteralString", _expand_query(file_path.read_text(encoding="utf-8")))  # type: ignore[redundant-cast]
    with conn.cursor(row_factory=class_row(model)) as cur:
        return cur.execute(query).fetchall()


class Loader(Protocol):
    """
    The shared shape of every object-kind loader: read from the connection and populate
    the DbInfo being assembled. Loaders run in a dependency-significant order (schemas
    and tables before the objects that attach to them).
    """

    def __call__(self, conn: psycopg.Connection[Any], db_info: DbInfo) -> None: ...


class Guard(Protocol):
    """
    A precondition check run before any loader: return a human-readable finding for each
    object the database contains that pgmig cannot process (an unsupported kind, an
    invalid index). An empty list means the guard passed. Findings from every guard are
    collected and reported together so the user sees all problems at once.
    """

    def __call__(self, conn: psycopg.Connection[Any]) -> list[str]: ...
