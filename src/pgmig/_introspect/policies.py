from pgmig._introspect._context import context
from pgmig._introspect._core import IntrospectionQuery, IntrospectionRowWithSchema, run_introspection_query
from pgmig._models import Policy


class _PolicyRow(IntrospectionRowWithSchema):
    table_name: str
    policy_name: str
    policy_command: str  # polcmd: 'r'/'a'/'w'/'d'/'*'
    policy_permissive: bool
    policy_roles: list[str]  # role names; empty means PUBLIC
    policy_using: str | None
    policy_check: str | None
    policy_comment: str | None


async def load() -> None:
    """
    Row-level security policies (pg_policy), attached to their owning table. Runs after tables
    are loaded so the owner lookup resolves.
    """
    for row in await run_introspection_query(IntrospectionQuery.POLICIES, _PolicyRow):
        table = context.db_introspection_result.schema_by_name[row.schema_name].table_by_name[row.table_name]
        table.policy_by_name[row.policy_name] = Policy(
            name=row.policy_name,
            command=row.policy_command,
            permissive=row.policy_permissive,
            roles=row.policy_roles,
            using=row.policy_using,
            check=row.policy_check,
            comment=row.policy_comment,
        )
