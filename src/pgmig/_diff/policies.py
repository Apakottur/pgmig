from collections.abc import Iterator

from pgmig._diff._core import Phase, Statement, ctx_iter_table_pairs, diff_child_comment_statements
from pgmig._models import Policy
from pgmig._sql import ident, qualified


def _render_create(table: str, name: str, policy: Policy) -> str:
    """
    Render CREATE POLICY <name> ON <table> [clauses]. A policy relying only on defaults
    (PERMISSIVE, FOR ALL, TO PUBLIC, no USING/CHECK) has an empty clause body.
    """
    body = policy.definition
    return f"CREATE POLICY {ident(name)} ON {table}{f' {body}' if body else ''};"


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of row-level security policies (a table-child object). Drops are
    phased before the table / columns / functions a policy references are dropped; creates after
    those exist. A definition change recreates (DROP + CREATE); ALTER POLICY forms are not used,
    so a rename shows as a drop plus a create.

    Roles are not modelled by pgmig: a CREATE POLICY that names a role (TO <role>) will fail at
    apply time if that role is absent on the target database. This is an accepted limitation.
    """
    for schema_name, table_name, src_table, dst_table in ctx_iter_table_pairs():
        # Table dropped: its policies are dropped with it.
        if dst_table is None:
            continue
        src = src_table.policy_by_name if src_table else {}
        dst = dst_table.policy_by_name
        table = qualified(schema_name, table_name)

        # A policy whose definition changed is dropped and recreated (no ALTER form). `changed`
        # feeds the comment diff too: a recreate resets the comment, so it must be re-emitted.
        changed = {name for name in src.keys() & dst.keys() if src[name].definition != dst[name].definition}
        dropped = sorted((src.keys() - dst.keys()) | changed)
        created = sorted((dst.keys() - src.keys()) | changed)

        for name in dropped:
            yield Statement(Phase.POLICY_DROP, f"DROP POLICY {ident(name)} ON {table};")

        comments = diff_child_comment_statements(schema_name, table_name, src, dst, kind="POLICY", recreated=changed)
        creates = [_render_create(table, name, dst[name]) for name in created]
        for sql in (*creates, *comments):
            yield Statement(Phase.POLICY_CREATE, sql)
