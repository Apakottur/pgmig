from enum import Enum, auto
from functools import lru_cache
from pathlib import Path
from typing import Protocol, TypeVar, assert_never

from pydantic import BaseModel, ConfigDict

from pgmig._introspect._context import context

# Static introspection queries dir.
_QUERIES_DIR = Path(__file__).parent / "queries"


@lru_cache
def _read_query(file_name: str) -> str:
    return (_QUERIES_DIR / file_name).read_text(encoding="utf-8")


class IntrospectionQueryType(Enum):
    """
    Introspection query type.
    """

    # Inspect the database before any loader runs and report what pgmig cannot process.
    GUARD = auto()

    # Populate the DB model.
    LOAD = auto()


class IntrospectionQueryConfig(BaseModel):
    """
    Configuration for an introspection query.
    """

    file_name: str
    kind: IntrospectionQueryType


class IntrospectionQuery(Enum):
    """
    All the introspection queries.
    """

    # Guards, run before any loader.
    PREFLIGHT = auto()
    UNSUPPORTED = auto()
    INVALID_INDEXES = auto()
    MATVIEW_DEPENDENCIES_CHECK = auto()

    # Loaders, in dependency-significant order.
    SCHEMAS = auto()
    TABLES = auto()
    INDEXES = auto()
    MATVIEW_INDEXES = auto()
    CONSTRAINTS = auto()
    SEQUENCES = auto()
    FUNCTIONS = auto()
    ENUMS = auto()
    ENUM_DEPENDENCIES = auto()
    VIEWS = auto()
    MATERIALIZED_VIEWS = auto()
    VIEW_DEPENDENCIES = auto()
    VIEW_COLUMN_DEPENDENCIES = auto()
    MATVIEW_DEPENDENCIES_LOAD = auto()
    TRIGGERS = auto()
    POLICIES = auto()
    DOMAINS = auto()
    COMPOSITE_TYPES = auto()
    COMPOSITE_TYPE_DEPENDENCIES = auto()
    RANGE_TYPES = auto()
    EXTENSIONS = auto()
    DEFAULT_PRIVILEGES = auto()


def get_introspection_query_config(query: IntrospectionQuery) -> IntrospectionQueryConfig:
    match query:
        case IntrospectionQuery.PREFLIGHT:
            return IntrospectionQueryConfig(file_name="preflight.sql", kind=IntrospectionQueryType.GUARD)
        case IntrospectionQuery.UNSUPPORTED:
            return IntrospectionQueryConfig(file_name="unsupported.sql", kind=IntrospectionQueryType.GUARD)
        case IntrospectionQuery.INVALID_INDEXES:
            return IntrospectionQueryConfig(file_name="invalid_indexes.sql", kind=IntrospectionQueryType.GUARD)
        case IntrospectionQuery.MATVIEW_DEPENDENCIES_CHECK:
            return IntrospectionQueryConfig(file_name="matview_dependencies.sql", kind=IntrospectionQueryType.GUARD)
        case IntrospectionQuery.SCHEMAS:
            return IntrospectionQueryConfig(file_name="schemas.sql", kind=IntrospectionQueryType.LOAD)
        case IntrospectionQuery.TABLES:
            return IntrospectionQueryConfig(file_name="tables.sql", kind=IntrospectionQueryType.LOAD)
        case IntrospectionQuery.INDEXES:
            return IntrospectionQueryConfig(file_name="indexes.sql", kind=IntrospectionQueryType.LOAD)
        case IntrospectionQuery.MATVIEW_INDEXES:
            return IntrospectionQueryConfig(file_name="matview_indexes.sql", kind=IntrospectionQueryType.LOAD)
        case IntrospectionQuery.CONSTRAINTS:
            return IntrospectionQueryConfig(file_name="constraints.sql", kind=IntrospectionQueryType.LOAD)
        case IntrospectionQuery.SEQUENCES:
            return IntrospectionQueryConfig(file_name="sequences.sql", kind=IntrospectionQueryType.LOAD)
        case IntrospectionQuery.FUNCTIONS:
            return IntrospectionQueryConfig(file_name="functions.sql", kind=IntrospectionQueryType.LOAD)
        case IntrospectionQuery.ENUMS:
            return IntrospectionQueryConfig(file_name="enums.sql", kind=IntrospectionQueryType.LOAD)
        case IntrospectionQuery.ENUM_DEPENDENCIES:
            return IntrospectionQueryConfig(file_name="enum_dependencies.sql", kind=IntrospectionQueryType.LOAD)
        case IntrospectionQuery.VIEWS:
            return IntrospectionQueryConfig(file_name="views.sql", kind=IntrospectionQueryType.LOAD)
        case IntrospectionQuery.MATERIALIZED_VIEWS:
            return IntrospectionQueryConfig(file_name="materialized_views.sql", kind=IntrospectionQueryType.LOAD)
        case IntrospectionQuery.VIEW_DEPENDENCIES:
            return IntrospectionQueryConfig(file_name="view_dependencies.sql", kind=IntrospectionQueryType.LOAD)
        case IntrospectionQuery.VIEW_COLUMN_DEPENDENCIES:
            return IntrospectionQueryConfig(file_name="view_column_dependencies.sql", kind=IntrospectionQueryType.LOAD)
        case IntrospectionQuery.MATVIEW_DEPENDENCIES_LOAD:
            return IntrospectionQueryConfig(file_name="matview_dependencies.sql", kind=IntrospectionQueryType.LOAD)
        case IntrospectionQuery.TRIGGERS:
            return IntrospectionQueryConfig(file_name="triggers.sql", kind=IntrospectionQueryType.LOAD)
        case IntrospectionQuery.POLICIES:
            return IntrospectionQueryConfig(file_name="policies.sql", kind=IntrospectionQueryType.LOAD)
        case IntrospectionQuery.DOMAINS:
            return IntrospectionQueryConfig(file_name="domains.sql", kind=IntrospectionQueryType.LOAD)
        case IntrospectionQuery.COMPOSITE_TYPES:
            return IntrospectionQueryConfig(file_name="composite_types.sql", kind=IntrospectionQueryType.LOAD)
        case IntrospectionQuery.COMPOSITE_TYPE_DEPENDENCIES:
            return IntrospectionQueryConfig(
                file_name="composite_type_dependencies.sql", kind=IntrospectionQueryType.LOAD
            )
        case IntrospectionQuery.RANGE_TYPES:
            return IntrospectionQueryConfig(file_name="range_types.sql", kind=IntrospectionQueryType.LOAD)
        case IntrospectionQuery.EXTENSIONS:
            return IntrospectionQueryConfig(file_name="extensions.sql", kind=IntrospectionQueryType.LOAD)
        case IntrospectionQuery.DEFAULT_PRIVILEGES:
            return IntrospectionQueryConfig(file_name="default_privileges.sql", kind=IntrospectionQueryType.LOAD)
        case _:
            assert_never(query)


class IntrospectionRow(BaseModel):
    """
    Base for every model parsed from a bundled SQL query -- a top-level row, or a nested
    jsonb object a query builds.
    """

    model_config = ConfigDict(
        # Ensure queries dont fetch unused columns.
        extra="forbid",
    )


class IntrospectionRowWithSchema(IntrospectionRow):
    """
    Base for every top-level row that carries a required schema in `schema_name` -- the schema an
    object belongs to. A shared base so that schema-bearing rows can be told apart from the rest
    (dependency rows carry a pair of schemas, a few carry none).
    """

    schema_name: str


class Loader(Protocol):
    """
    The shared shape of every object-kind loader: read from the connection and populate
    the DB introspection result being assembled. Loaders run in a dependency-significant order (schemas
    and tables before the objects that attach to them).
    """

    async def __call__(self) -> None: ...


class Guard(Protocol):
    """
    A precondition check run before any loader: return a human-readable finding for each
    object the database contains that pgmig cannot process (an unsupported kind, an
    invalid index). An empty list means the guard passed. Findings from every guard are
    collected and reported together so the user sees all problems at once.
    """

    async def __call__(self) -> list[str]: ...


_RowT = TypeVar("_RowT", bound=IntrospectionRow)


async def run_introspection_query(query: IntrospectionQuery, model: type[_RowT]) -> list[_RowT]:
    """
    Run the given introspection query, parsing each row into the given model.
    """
    return await context.conn.introspect(_read_query(get_introspection_query_config(query).file_name), model)
