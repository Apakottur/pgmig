from collections.abc import Iterable

from pgmig._models import Grant
from pgmig._sql import ident


def _render_grantee(grantee: str) -> str:
    """PUBLIC is a pseudo-role keyword, not an identifier; every real role name is quoted."""
    return "PUBLIC" if grantee == "PUBLIC" else ident(grantee)


def grant_statements(
    kind: str,
    qualified_name: str,
    src_grants: Iterable[Grant],
    dst_grants: Iterable[Grant],
    src_owner: str,
    dst_owner: str,
    *,
    include_named_roles: bool,
) -> list[str]:
    """
    Reconcile an object's ACL from source to target.

    Emits REVOKE for privileges present only in the source, GRANT (with WITH GRANT OPTION when
    grantable) for those present only in the target, and -- when a privilege is on both sides
    but its grant option differs -- a targeted REVOKE GRANT OPTION FOR / GRANT ... WITH GRANT
    OPTION so a grant-option-only change is not a full revoke-then-grant.

    Each side's owner self-grants are excluded: the owner's privileges are implied by ownership
    and reconciled by ALTER ... OWNER TO, so including them would churn a full revoke-then-grant
    on every owner change (and duplicate what the owner change already transfers).

    PUBLIC grants are always diffed -- PUBLIC exists on every cluster, so they are portable and
    apply-safe, and catching missing/extra PUBLIC access (e.g. a missing REVOKE ... FROM PUBLIC)
    is security-relevant. Named-role grants are diffed only when `include_named_roles` is set:
    they reference cluster-level roles that diverge across environments and fail at apply when the
    role is absent on the target, so they are opt-in (the --include-grants flag), mirroring owner.

    `kind` is the GRANT/REVOKE object keyword ("TABLE", "SEQUENCE", "SCHEMA", "FUNCTION").
    Statements are ordered revokes-then-grants, each by (grantee, privilege), for determinism.
    """
    src_by_key = {(g.grantee, g.privilege): g for g in src_grants if g.grantee != src_owner}
    dst_by_key = {(g.grantee, g.privilege): g for g in dst_grants if g.grantee != dst_owner}

    revokes: list[str] = []
    grants: list[str] = []
    for grantee, privilege in sorted(src_by_key.keys() | dst_by_key.keys()):
        # PUBLIC is always reconciled; named roles only when opted in.
        if grantee != "PUBLIC" and not include_named_roles:
            continue
        src = src_by_key.get((grantee, privilege))
        dst = dst_by_key.get((grantee, privilege))
        target = f"{privilege} ON {kind} {qualified_name}"
        who = _render_grantee(grantee)
        if dst is None:
            revokes.append(f"REVOKE {target} FROM {who};")
        elif src is None:
            option = " WITH GRANT OPTION" if dst.grantable else ""
            grants.append(f"GRANT {target} TO {who}{option};")
        elif src.grantable and not dst.grantable:
            revokes.append(f"REVOKE GRANT OPTION FOR {target} FROM {who};")
        elif dst.grantable and not src.grantable:
            grants.append(f"GRANT {target} TO {who} WITH GRANT OPTION;")
    return revokes + grants
