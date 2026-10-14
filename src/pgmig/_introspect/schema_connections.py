from pgmig._introspect._context import context
from pgmig._introspect._core import Guard
from pgmig._introspect._rows import IntrospectionRow


class _ConnectionRow(IntrospectionRow):
    obj_schema: str
    obj_identity: str
    ref_schema: str
    ref_identity: str


class SchemaConnectionsGuard(Guard[_ConnectionRow]):
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

    file_name = "schema_connections.sql"
    model = _ConnectionRow

    @classmethod
    def process_rows(cls, rows: list[_ConnectionRow]) -> list[str]:
        ignore = context().ignore_schemas
        findings: set[str] = set()
        for row in rows:
            if (row.obj_schema in ignore) != (row.ref_schema in ignore):
                findings.add(f"{row.obj_identity} depends on {row.ref_identity}")
        return sorted(findings)
