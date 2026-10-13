from enum import Enum, auto
from functools import lru_cache
from pathlib import Path
from typing import Protocol, TypeVar

from pydantic import BaseModel, ConfigDict

from pgmig._introspect._context import context
from pgmig._models import Grant

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


class IntrospectionQuery(Enum):
    """
    All the introspection queries, each valued by its SQL file and kind.
    """

    # Guards, run before any loader.
    PREFLIGHT = ("preflight.sql", IntrospectionQueryType.GUARD)
    UNSUPPORTED = ("unsupported.sql", IntrospectionQueryType.GUARD)
    INVALID_INDEXES = ("invalid_indexes.sql", IntrospectionQueryType.GUARD)
    MATVIEW_DEPENDENCIES = ("matview_dependencies.sql", IntrospectionQueryType.GUARD)
    SCHEMA_CONNECTIONS = ("schema_connections.sql", IntrospectionQueryType.GUARD)

    # Loaders. Their run order is set by _engine._IntrospectionPreflight.get_loaders, not here.
    SCHEMAS = ("schemas.sql", IntrospectionQueryType.LOAD)
    TABLES = ("tables.sql", IntrospectionQueryType.LOAD)
    INDEXES = ("indexes.sql", IntrospectionQueryType.LOAD)
    MATVIEW_INDEXES = ("matview_indexes.sql", IntrospectionQueryType.LOAD)
    CONSTRAINTS = ("constraints.sql", IntrospectionQueryType.LOAD)
    SEQUENCES = ("sequences.sql", IntrospectionQueryType.LOAD)
    FUNCTIONS = ("functions.sql", IntrospectionQueryType.LOAD)
    ENUMS = ("enums.sql", IntrospectionQueryType.LOAD)
    ENUM_DEPENDENCIES = ("enum_dependencies.sql", IntrospectionQueryType.LOAD)
    VIEWS = ("views.sql", IntrospectionQueryType.LOAD)
    VIEW_DEPENDENCIES = ("view_dependencies.sql", IntrospectionQueryType.LOAD)
    VIEW_COLUMN_DEPENDENCIES = ("view_column_dependencies.sql", IntrospectionQueryType.LOAD)
    TRIGGERS = ("triggers.sql", IntrospectionQueryType.LOAD)
    POLICIES = ("policies.sql", IntrospectionQueryType.LOAD)
    DOMAINS = ("domains.sql", IntrospectionQueryType.LOAD)
    COMPOSITE_TYPES = ("composite_types.sql", IntrospectionQueryType.LOAD)
    COMPOSITE_TYPE_DEPENDENCIES = ("composite_type_dependencies.sql", IntrospectionQueryType.LOAD)
    RANGE_TYPES = ("range_types.sql", IntrospectionQueryType.LOAD)
    EXTENSIONS = ("extensions.sql", IntrospectionQueryType.LOAD)
    DEFAULT_PRIVILEGES = ("default_privileges.sql", IntrospectionQueryType.LOAD)

    def __init__(self, file_name: str, kind: IntrospectionQueryType) -> None:
        self.file_name = file_name
        self.kind = kind


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


class GrantRow(IntrospectionRow):
    """
    One effective privilege of an object's ACL (jsonb object built by the queries).
    """

    grantee: str
    privilege: str
    grantable: bool


def grants(rows: list[GrantRow]) -> frozenset[Grant]:
    """
    Convert parsed ACL rows into the model's grant set.
    """
    return frozenset(Grant(grantee=row.grantee, privilege=row.privilege, grantable=row.grantable) for row in rows)


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
    # Get the query SQL.
    sql = _read_query(query.file_name)

    # Run the query.
    rows = await context.conn.introspect(sql, model)

    # Filter out rows in ignored schemas.
    ignored_schemas = context.ignore_schemas
    if query.kind is IntrospectionQueryType.LOAD:
        filtered_rows = []
        for row in rows:
            if isinstance(row, IntrospectionRowWithSchema) and row.schema_name in ignored_schemas:
                continue
            filtered_rows.append(row)
        rows = filtered_rows

    return rows
