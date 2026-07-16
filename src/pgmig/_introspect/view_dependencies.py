from pgmig._introspect._context import context
from pgmig._introspect._core import _QueryRow, run_introspection_query
from pgmig._keys import ViewKey
from pgmig._sql import qualified

# pg_class.relkind -> the object noun used in the finding message.
_KIND_LABEL = {"v": "view", "m": "materialized view"}


class _ViewDependencyRow(_QueryRow):
    dependent_schema: str
    dependent_view: str
    referenced_schema: str
    referenced_view: str


class _MatviewDependencyRow(_QueryRow):
    dependent_schema: str
    dependent_view: str
    dependent_kind: str
    referenced_schema: str
    referenced_view: str
    referenced_kind: str


async def load() -> None:
    """
    View-on-view edges: record, for each plain view that reads another plain view, the set
    of views it reads from. The view diff uses these to topologically order CREATE
    (dependencies first) and DROP (dependents first) within the view phases. Dependencies
    involving a materialized view are rejected by `check`, not ordered.
    """
    for row in await run_introspection_query("view_dependencies.sql", _ViewDependencyRow):
        dependent = ViewKey(row.dependent_schema, row.dependent_view)
        referenced = ViewKey(row.referenced_schema, row.referenced_view)
        context.db_introspection_result.view_dependencies.setdefault(dependent, set()).add(referenced)


async def check() -> list[str]:
    """
    Guard: report a dependency where a materialized view reads, or is read by, another view
    or matview. Plain view-on-view dependencies are ordered by a topological sort (see
    `load`); matviews are not folded into that sort yet, so a matview-involving pair is
    reported rather than emitted in a possibly-wrong order.
    """
    findings: list[str] = []
    for row in await run_introspection_query("matview_dependencies.sql", _MatviewDependencyRow):
        dependent = qualified(row.dependent_schema, row.dependent_view)
        referenced = qualified(row.referenced_schema, row.referenced_view)
        dependent_label = _KIND_LABEL[row.dependent_kind]
        referenced_label = _KIND_LABEL[row.referenced_kind]
        findings.append(
            f"{dependent_label} {dependent} reads from {referenced_label} {referenced}: "
            f"dependencies involving materialized views are not supported yet"
        )
    return findings
