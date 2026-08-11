from collections.abc import Iterator
from typing import cast

from pgmig._diff._context import context
from pgmig._diff._core import Phase, Statement
from pgmig._diff.grants import _render_grantee
from pgmig._keys import DefaultAclKey
from pgmig._models import DefaultAcl, Grant
from pgmig._sql import ident


def _reconcile(
    key: DefaultAclKey,
    object_type: str,
    src_grants: frozenset[Grant],
    dst_grants: frozenset[Grant],
    *,
    include_named_roles: bool,
) -> list[str]:
    """
    Reconcile one default-privilege rule's effective ACL from source to target, emitting
    ALTER DEFAULT PRIVILEGES ... GRANT/REVOKE statements.

    The defaclrole's own self-grants are excluded (they are the role's implicit baseline and
    are identical on both sides), mirroring the owner-self-grant exclusion in object grants.
    PUBLIC grantees are always reconciled; named-role grantees only under --include-grants --
    matching grant_statements. Note the statement always names FOR ROLE <role>, which must
    exist on the target at apply time.
    """
    prefix = f"ALTER DEFAULT PRIVILEGES FOR ROLE {ident(key.role)}"
    if key.schema is not None:
        prefix += f" IN SCHEMA {ident(key.schema)}"

    src_by_key = {(g.grantee, g.privilege): g for g in src_grants if g.grantee != key.role}
    dst_by_key = {(g.grantee, g.privilege): g for g in dst_grants if g.grantee != key.role}

    revokes: list[str] = []
    grants: list[str] = []
    for grantee, privilege in sorted(src_by_key.keys() | dst_by_key.keys()):
        if grantee != "PUBLIC" and not include_named_roles:
            continue
        src = src_by_key.get((grantee, privilege))
        dst = dst_by_key.get((grantee, privilege))
        target = f"{privilege} ON {object_type}"
        who = _render_grantee(grantee)
        if dst is None:
            revokes.append(f"{prefix} REVOKE {target} FROM {who};")
        elif src is None:
            option = " WITH GRANT OPTION" if dst.grantable else ""
            grants.append(f"{prefix} GRANT {target} TO {who}{option};")
        elif src.grantable and not dst.grantable:
            revokes.append(f"{prefix} REVOKE GRANT OPTION FOR {target} FROM {who};")
        elif dst.grantable and not src.grantable:
            grants.append(f"{prefix} GRANT {target} TO {who} WITH GRANT OPTION;")
    return revokes + grants


def generate() -> Iterator[Statement]:
    """
    Generate the migration SQL of ALTER DEFAULT PRIVILEGES rules (pg_default_acl).

    A rule present on only one side is compared against the built-in baseline on the other:
    each side's effective ACL is its own row's grants, or -- when that side has no row -- the
    baseline (acldefault) carried by the side that does. Diffing effective-vs-effective this
    way turns "source configured extra grants, target has none" into the REVOKEs that undo
    them, and vice versa, without a row on both sides.

    Emitted in the GRANT phase, after schema creates (an IN SCHEMA rule needs its schema) and
    every other object; default-privilege rules affect only future objects, so they have no
    other ordering dependency.
    """
    src_map = context.source.default_acl_by_key
    dst_map = context.target.default_acl_by_key

    # None-safe sort: a global rule (schema None) sorts before any schema-scoped one.
    for key in sorted(src_map.keys() | dst_map.keys(), key=lambda k: (k.role, k.schema or "", k.object_type)):
        src_rule = src_map.get(key)
        dst_rule = dst_map.get(key)
        # The baseline is deterministic in (object type, role), so either side's row carries the
        # same one; the side without a row falls back to it. The key came from the union of both
        # maps, so at least one side has a row (cast away the Optional the checker sees).
        present = cast("DefaultAcl", src_rule if src_rule is not None else dst_rule)
        src_grants = src_rule.grants if src_rule is not None else present.baseline
        dst_grants = dst_rule.grants if dst_rule is not None else present.baseline
        for sql in _reconcile(
            key,
            present.object_type,
            src_grants,
            dst_grants,
            include_named_roles=context.include_grants,
        ):
            yield Statement(Phase.GRANT, sql)
