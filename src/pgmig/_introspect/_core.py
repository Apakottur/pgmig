from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Protocol, TypeVar

from pydantic import BaseModel, ConfigDict

from pgmig._introspect._context import context

# Static introspection queries dir.
_QUERIES_DIR = Path(__file__).parent / "queries"


@lru_cache
def _read_query(file_name: str) -> str:
    return (_QUERIES_DIR / file_name).read_text(encoding="utf-8")


class QueryKind(Enum):
    """
    How an introspection query is used. A loader populates the model; a guard inspects the
    database before any loader runs and reports what pgmig cannot process (the preflight, which
    only detects which object classes exist, counts as a guard here).
    """

    LOAD = "load"
    GUARD = "guard"


class IntrospectionQuery(Enum):
    """
    Every bundled introspection query, paired with its SQL file and how it is used. The single
    place that maps a query to its file name -- callers pass a member, never a raw file name.

    `matview_dependencies.sql` backs two members: the loader records matview-as-reader edges, the
    guard refuses a plain view that reads a matview.
    """

    file_name: str
    kind: QueryKind

    def __init__(self, file_name: str, kind: QueryKind) -> None:
        self.file_name = file_name
        self.kind = kind

    # Loaders, in dependency-significant order (see _engine.get_loaders).
    SCHEMAS = ("schemas.sql", QueryKind.LOAD)
    TABLES = ("tables.sql", QueryKind.LOAD)
    INDEXES = ("indexes.sql", QueryKind.LOAD)
    MATVIEW_INDEXES = ("matview_indexes.sql", QueryKind.LOAD)
    CONSTRAINTS = ("constraints.sql", QueryKind.LOAD)
    SEQUENCES = ("sequences.sql", QueryKind.LOAD)
    FUNCTIONS = ("functions.sql", QueryKind.LOAD)
    ENUMS = ("enums.sql", QueryKind.LOAD)
    ENUM_DEPENDENCIES = ("enum_dependencies.sql", QueryKind.LOAD)
    VIEWS = ("views.sql", QueryKind.LOAD)
    MATERIALIZED_VIEWS = ("materialized_views.sql", QueryKind.LOAD)
    VIEW_DEPENDENCIES = ("view_dependencies.sql", QueryKind.LOAD)
    VIEW_COLUMN_DEPENDENCIES = ("view_column_dependencies.sql", QueryKind.LOAD)
    MATVIEW_DEPENDENCIES_LOAD = ("matview_dependencies.sql", QueryKind.LOAD)
    TRIGGERS = ("triggers.sql", QueryKind.LOAD)
    POLICIES = ("policies.sql", QueryKind.LOAD)
    DOMAINS = ("domains.sql", QueryKind.LOAD)
    COMPOSITE_TYPES = ("composite_types.sql", QueryKind.LOAD)
    COMPOSITE_TYPE_DEPENDENCIES = ("composite_type_dependencies.sql", QueryKind.LOAD)
    RANGE_TYPES = ("range_types.sql", QueryKind.LOAD)
    EXTENSIONS = ("extensions.sql", QueryKind.LOAD)
    DEFAULT_PRIVILEGES = ("default_privileges.sql", QueryKind.LOAD)

    # Guards, run before any loader.
    PREFLIGHT = ("preflight.sql", QueryKind.GUARD)
    UNSUPPORTED = ("unsupported.sql", QueryKind.GUARD)
    INVALID_INDEXES = ("invalid_indexes.sql", QueryKind.GUARD)
    MATVIEW_DEPENDENCIES_CHECK = ("matview_dependencies.sql", QueryKind.GUARD)


class _IntrospectionRow(BaseModel):
    """
    Base for every model parsed from a bundled SQL query -- a top-level row, or a nested
    jsonb object a query builds.
    """

    model_config = ConfigDict(
        # Ensure queries dont fetch unused columns.
        extra="forbid",
    )


class _IntrospectionRowWithSchema(_IntrospectionRow):
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


_RowT = TypeVar("_RowT", bound=_IntrospectionRow)


async def run_introspection_query(query: IntrospectionQuery, model: type[_RowT]) -> list[_RowT]:
    """
    Run the given introspection query, parsing each row into the given model.
    """
    return await context.conn.introspect(_read_query(query.file_name), model)
