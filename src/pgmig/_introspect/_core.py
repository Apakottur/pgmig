import asyncio
from abc import ABC, abstractmethod
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any, Generic, TypeVar

from pgmig._introspect._context import context
from pgmig._introspect._rows import IntrospectionRow, IntrospectionRowWithSchema

# Static introspection queries dir.
_QUERIES_DIR = Path(__file__).parent / "queries"


@lru_cache
def _read_query(file_name: str) -> str:
    return (_QUERIES_DIR / file_name).read_text(encoding="utf-8")


_RowT = TypeVar("_RowT", bound=IntrospectionRow)
_ResultT = TypeVar("_ResultT")


class IntrospectionQuery(ABC, Generic[_RowT, _ResultT]):
    """
    An introspection query: its SQL file, the model its rows parse into, and how its parsed rows are processed.
    """

    # The query SQL file, in the queries dir.
    file_name: str

    # The model each row is parsed into.
    model: type[_RowT]

    # Whether rows in ignored schemas are dropped before processing.
    filter_ignored_schemas: bool = False

    @classmethod
    @abstractmethod
    def process_rows(cls, rows: list[_RowT]) -> _ResultT:
        """
        Process the parsed rows of the query.
        """


class Guard(IntrospectionQuery[_RowT, list[str]]):
    """
    A precondition check run before any loader: return a human-readable finding for each
    object the database contains that pgmig cannot process (an unsupported kind, an
    invalid index). An empty list means the guard passed. Findings from every guard are
    collected and reported together so the user sees all problems at once.
    """


class Loader(IntrospectionQuery[_RowT, None]):
    """
    The shared shape of every object-kind loader: populate the DB introspection result being
    assembled from the query rows. Loaders run in a dependency-significant order (schemas
    and tables before the objects that attach to them).
    """

    filter_ignored_schemas = True


async def run_introspection_queries(
    queries: Sequence[type[IntrospectionQuery[Any, _ResultT]]], *, end_snapshot: bool
) -> list[_ResultT]:
    """
    Run the given introspection queries in a single round trip, and process the rows of each one, in order.
    With end_snapshot, the snapshot transaction ends before the rows are processed.
    """
    # Run all the queries.
    rows_per_query = await context().conn.introspect(
        [_read_query(query.file_name) for query in queries], end_snapshot=end_snapshot
    )

    # Process the rows of each query.
    results = []
    for query, rows in zip(queries, rows_per_query, strict=True):
        results.append(_process_rows(query, rows))

        # Processing does not await, so yield to the event loop between queries. Otherwise, introspecting the other
        # database concurrently stalls, and its snapshot transaction sits idle meanwhile.
        await asyncio.sleep(0)
    return results


async def run_introspection_query(query: type[IntrospectionQuery[_RowT, _ResultT]], *, end_snapshot: bool) -> _ResultT:
    """
    Run the given introspection query, and process its rows.
    """
    [result] = await run_introspection_queries([query], end_snapshot=end_snapshot)
    return result


def _process_rows(query: type[IntrospectionQuery[_RowT, _ResultT]], raw_rows: list[dict[str, Any]]) -> _ResultT:
    """
    Parse each row of the given introspection query into the query's model, and process the rows.
    """
    # Parse the rows.
    rows = [query.model.model_validate(raw_row) for raw_row in raw_rows]

    # Filter out rows in ignored schemas.
    ignored_schemas = context().ignore_schemas
    if query.filter_ignored_schemas:
        filtered_rows = []
        for row in rows:
            if isinstance(row, IntrospectionRowWithSchema) and row.schema_name in ignored_schemas:
                continue
            filtered_rows.append(row)
        rows = filtered_rows

    # Process the rows.
    return query.process_rows(rows)
