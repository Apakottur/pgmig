from collections.abc import Callable, Sequence
from enum import Enum, auto
from functools import lru_cache
from pathlib import Path
from typing import Any, TypeVar

from pgmig._introspect import (
    composite_type_dependencies,
    composite_types,
    constraints,
    default_privileges,
    domains,
    enum_dependencies,
    enums,
    extensions,
    functions,
    indexes,
    invalid_indexes,
    matview_dependencies,
    matview_indexes,
    policies,
    preflight,
    range_types,
    schema_connections,
    schemas,
    sequences,
    tables,
    triggers,
    unsupported,
    view_column_dependencies,
    view_dependencies,
    views,
)
from pgmig._introspect._context import context
from pgmig._introspect._rows import IntrospectionRow, IntrospectionRowWithSchema

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
    All the introspection queries, each valued by its SQL file, its kind, the model its rows parse into and the
    function processing the parsed rows.
    """

    # Guards, run before any loader.
    PREFLIGHT = ("preflight.sql", IntrospectionQueryType.GUARD, preflight.PreflightRow, preflight.load_rows)
    UNSUPPORTED = ("unsupported.sql", IntrospectionQueryType.GUARD, unsupported.UnsupportedRow, unsupported.check_rows)
    INVALID_INDEXES = (
        "invalid_indexes.sql",
        IntrospectionQueryType.GUARD,
        invalid_indexes.InvalidIndexRow,
        invalid_indexes.check_rows,
    )
    MATVIEW_DEPENDENCIES = (
        "matview_dependencies.sql",
        IntrospectionQueryType.GUARD,
        matview_dependencies.MatviewDependencyRow,
        matview_dependencies.check_rows,
    )
    SCHEMA_CONNECTIONS = (
        "schema_connections.sql",
        IntrospectionQueryType.GUARD,
        schema_connections.ConnectionRow,
        schema_connections.check_rows,
    )

    # Loaders. Their run order is set by _engine._get_loaders, not here.
    SCHEMAS = ("schemas.sql", IntrospectionQueryType.LOAD, schemas.SchemaRow, schemas.load_rows)
    TABLES = ("tables.sql", IntrospectionQueryType.LOAD, tables.TableRow, tables.load_rows)
    INDEXES = ("indexes.sql", IntrospectionQueryType.LOAD, indexes.IndexRow, indexes.load_rows)
    MATVIEW_INDEXES = ("matview_indexes.sql", IntrospectionQueryType.LOAD, indexes.IndexRow, matview_indexes.load_rows)
    CONSTRAINTS = ("constraints.sql", IntrospectionQueryType.LOAD, constraints.ConstraintRow, constraints.load_rows)
    SEQUENCES = ("sequences.sql", IntrospectionQueryType.LOAD, sequences.SequenceRow, sequences.load_rows)
    FUNCTIONS = ("functions.sql", IntrospectionQueryType.LOAD, functions.FunctionRow, functions.load_rows)
    ENUMS = ("enums.sql", IntrospectionQueryType.LOAD, enums.EnumRow, enums.load_rows)
    ENUM_DEPENDENCIES = (
        "enum_dependencies.sql",
        IntrospectionQueryType.LOAD,
        enum_dependencies.EnumDependencyRow,
        enum_dependencies.load_rows,
    )
    VIEWS = ("views.sql", IntrospectionQueryType.LOAD, views.ViewRow, views.load_rows)
    VIEW_DEPENDENCIES = (
        "view_dependencies.sql",
        IntrospectionQueryType.LOAD,
        view_dependencies.ViewDependencyRow,
        view_dependencies.load_rows,
    )
    VIEW_COLUMN_DEPENDENCIES = (
        "view_column_dependencies.sql",
        IntrospectionQueryType.LOAD,
        view_column_dependencies.ViewColumnDependencyRow,
        view_column_dependencies.load_rows,
    )
    TRIGGERS = ("triggers.sql", IntrospectionQueryType.LOAD, triggers.TriggerRow, triggers.load_rows)
    POLICIES = ("policies.sql", IntrospectionQueryType.LOAD, policies.PolicyRow, policies.load_rows)
    DOMAINS = ("domains.sql", IntrospectionQueryType.LOAD, domains.DomainRow, domains.load_rows)
    COMPOSITE_TYPES = (
        "composite_types.sql",
        IntrospectionQueryType.LOAD,
        composite_types.CompositeTypeRow,
        composite_types.load_rows,
    )
    COMPOSITE_TYPE_DEPENDENCIES = (
        "composite_type_dependencies.sql",
        IntrospectionQueryType.LOAD,
        composite_type_dependencies.CompositeTypeDependencyRow,
        composite_type_dependencies.load_rows,
    )
    RANGE_TYPES = ("range_types.sql", IntrospectionQueryType.LOAD, range_types.RangeTypeRow, range_types.load_rows)
    EXTENSIONS = ("extensions.sql", IntrospectionQueryType.LOAD, extensions.ExtensionRow, extensions.load_rows)
    DEFAULT_PRIVILEGES = (
        "default_privileges.sql",
        IntrospectionQueryType.LOAD,
        default_privileges.DefaultAclRow,
        default_privileges.load_rows,
    )

    def __init__(
        self,
        file_name: str,
        kind: IntrospectionQueryType,
        model: type[IntrospectionRow],
        process_rows: Callable[[list[Any]], Any],
    ) -> None:
        self.file_name = file_name
        self.kind = kind
        self.model = model
        self.process_rows = process_rows


_RowT = TypeVar("_RowT", bound=IntrospectionRow)


async def run_introspection_query(query: IntrospectionQuery, model: type[_RowT]) -> list[_RowT]:
    """
    Run the given introspection query, parsing each row into the given model.
    """
    # Get the query SQL.
    sql = _read_query(query.file_name)

    # Run the query.
    rows = await context().conn.introspect(sql, model)

    # Filter out rows in ignored schemas.
    ignored_schemas = context().ignore_schemas
    if query.kind is IntrospectionQueryType.LOAD:
        filtered_rows = []
        for row in rows:
            if isinstance(row, IntrospectionRowWithSchema) and row.schema_name in ignored_schemas:
                continue
            filtered_rows.append(row)
        rows = filtered_rows

    return rows


async def run_introspection_queries(queries: Sequence[IntrospectionQuery]) -> list[Any]:
    """
    Run the given introspection queries in order, returning what processing the rows of each one returned (a
    guard's findings, the preflight row, nothing for a loader).
    """
    results = []
    for query in queries:
        # Run the query.
        rows = await run_introspection_query(query, query.model)

        # Process its rows.
        results.append(query.process_rows(rows))

    return results
