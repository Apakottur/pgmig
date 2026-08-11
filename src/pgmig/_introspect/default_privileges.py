from pgmig._introspect._context import context
from pgmig._introspect._core import IntrospectionQuery, IntrospectionRow, run_introspection_query
from pgmig._keys import DefaultAclKey
from pgmig._models import DefaultAcl, Grant

# pg_default_acl.defaclobjtype -> the plural GRANT keyword. 'n' (SCHEMAS) is PG15+; a PG14
# cluster simply has no such rows, so the mapping is version-independent here.
_OBJECT_TYPE_KEYWORD = {
    "r": "TABLES",
    "S": "SEQUENCES",
    "f": "FUNCTIONS",
    "T": "TYPES",
    "n": "SCHEMAS",
}


class _GrantRow(IntrospectionRow):
    grantee: str
    privilege: str
    grantable: bool


class _DefaultAclRow(IntrospectionRow):
    role: str
    # None is a cluster-wide rule (not scoped to any schema); such a rule is never ignored.
    schema_name: str | None
    object_type: str  # defaclobjtype: 'r' / 'S' / 'f' / 'T' / 'n'
    grants: list[_GrantRow]
    baseline_grants: list[_GrantRow]


def _grants(rows: list[_GrantRow]) -> frozenset[Grant]:
    return frozenset(Grant(grantee=row.grantee, privilege=row.privilege, grantable=row.grantable) for row in rows)


async def load() -> None:
    """
    ALTER DEFAULT PRIVILEGES rules (pg_default_acl, database-level).
    """
    for row in await run_introspection_query(IntrospectionQuery.DEFAULT_PRIVILEGES, _DefaultAclRow):
        # schema_name is optional here (None = a cluster-wide rule), so the row is not an
        # IntrospectionRowWithSchema and run_introspection_query does not drop it; skip a rule
        # scoped to an ignored schema.
        if row.schema_name in context.ignore_schemas:
            continue
        key = DefaultAclKey(role=row.role, schema=row.schema_name, object_type=row.object_type)
        context.db_introspection_result.default_acl_by_key[key] = DefaultAcl(
            role=row.role,
            schema=row.schema_name,
            object_type=_OBJECT_TYPE_KEYWORD[row.object_type],
            grants=_grants(row.grants),
            baseline=_grants(row.baseline_grants),
        )
