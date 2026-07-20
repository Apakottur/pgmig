from pgmig._introspect._core import _IntrospectionRow, run_introspection_query
from pgmig._sql import qualified

# Human-readable name per unsupported kind, keyed by (catalog, code). The same single-char
# code is reused across catalogs (e.g. 'r' is a plain table in pg_class but a rule in
# pg_rewrite), so the catalog is part of the key -- a flat single-char map would collide.
_KIND_NAMES = {
    ("pg_class", "f"): "foreign table",
    ("pg_type", "b"): "base type",
    ("pg_proc", "a"): "aggregate",
    ("pg_proc", "w"): "window function",
    ("pg_rewrite", "r"): "rule",
    ("pg_class", "inherits"): "legacy inheritance child table",
    ("pg_statistic_ext", "e"): "extended statistics",
    ("pg_event_trigger", "e"): "event trigger",
}


class _UnsupportedRow(_IntrospectionRow):
    # schema_name is None for database-global objects (e.g. event triggers).
    schema_name: str | None
    obj_name: str
    catalog: str
    kind: str


async def check() -> list[str]:
    """
    Guard: report object kinds that are not modelled yet (see unsupported.sql for the full
    list: foreign tables, base types, aggregate/window
    functions, rules, legacy
    inheritance children, extended statistics, event triggers). Without this, generate()
    diffs only the supported kinds and returns "" for a database whose not-yet-modelled
    objects differ on one side, falsely claiming convergence.
    """
    findings = []
    for row in await run_introspection_query("unsupported.sql", _UnsupportedRow):
        name = _KIND_NAMES.get((row.catalog, row.kind), row.kind)
        parts = [row.schema_name, row.obj_name] if row.schema_name is not None else [row.obj_name]
        findings.append(f"{name} {qualified(*parts)} is not supported yet")
    return findings
