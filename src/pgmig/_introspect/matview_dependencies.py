from pgmig._introspect._context import context
from pgmig._introspect._core import _QueryRow, run_introspection_query
from pgmig._keys import ViewKey
from pgmig._sql import qualified

# pg_class.relkind -> the object noun used in the finding message.
_KIND_LABEL = {"v": "view", "m": "materialized view"}


class _MatviewDependencyRow(_QueryRow):
    dependent_schema: str
    dependent_view: str
    dependent_kind: str
    referenced_schema: str
    referenced_view: str
    referenced_kind: str


async def load() -> None:
    """
    Matview-as-reader edges: record, for each materialized view that reads another view or
    matview, the set of relations it reads from. The matview diff uses these to topologically
    order CREATE (dependencies first) and DROP (dependents first) among matviews, and to
    cascade the recreate set.

    Every row this sees has a matview dependent: `check` runs first and refuses the database if
    any row has a plain-view dependent (a view reading a matview), so a loader only ever runs
    once that pairing is ruled out.
    """
    for row in await run_introspection_query("matview_dependencies.sql", _MatviewDependencyRow):
        dependent = ViewKey(row.dependent_schema, row.dependent_view)
        referenced = ViewKey(row.referenced_schema, row.referenced_view)
        context.db_introspection_result.matview_dependencies.setdefault(dependent, set()).add(referenced)


async def check() -> list[str]:
    """
    Guard: report a plain view that reads a materialized view. A matview is created in a later
    phase than plain views (and dropped in an earlier one), so a view cannot be ordered before
    the matview it reads -- that pairing stays unsupported. Matview-as-reader edges (a matview
    reading a view or matview) are ordered instead, by `load`.
    """
    findings: list[str] = []
    for row in await run_introspection_query("matview_dependencies.sql", _MatviewDependencyRow):
        if row.dependent_kind == "m":
            continue
        dependent = qualified(row.dependent_schema, row.dependent_view)
        referenced = qualified(row.referenced_schema, row.referenced_view)
        dependent_label = _KIND_LABEL[row.dependent_kind]
        referenced_label = _KIND_LABEL[row.referenced_kind]
        findings.append(
            f"{dependent_label} {dependent} reads from {referenced_label} {referenced}: "
            f"a plain view reading a materialized view is not supported"
        )
    return findings
