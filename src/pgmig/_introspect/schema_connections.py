from pgmig._introspect._context import context
from pgmig._introspect._core import IntrospectionQuery, IntrospectionRow, run_introspection_query


class _ConnectionRow(IntrospectionRow):
    obj_schema: str
    obj_identity: str
    ref_schema: str
    ref_identity: str


async def check() -> list[str]:
    """
    Report dependency edges that connect an ignored schema to a kept one, in either direction.

    Ignoring a schema that is not isolated would emit a migration that fails at apply -- e.g. a
    DROP/recreate in a kept schema blocked by an object in the ignored schema that still depends
    on it, or a kept object referencing an ignored one pgmig no longer manages. Rather than emit
    such a migration (or silently drop the edge), `--ignore-schema` refuses a connected schema.

    Runs only when at least one schema is ignored. A pair with both endpoints ignored is not a
    connection to a kept schema, so it is allowed; only an edge with exactly one ignored endpoint
    crosses the boundary.
    """
    ignore = context.ignore_schemas
    findings: set[str] = set()
    for row in await run_introspection_query(IntrospectionQuery.SCHEMA_CONNECTIONS, _ConnectionRow):
        if (row.obj_schema in ignore) != (row.ref_schema in ignore):
            findings.add(f"{row.obj_identity} depends on {row.ref_identity}")
    return sorted(findings)
