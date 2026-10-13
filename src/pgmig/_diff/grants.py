from collections.abc import Iterable, Iterator
from typing import Protocol

from pgmig._diff._context import context
from pgmig._diff._core import Phase, Statement, owner_statements
from pgmig._models import Grant
from pgmig._sql import ident


def _render_grantee(grantee: str) -> str:
    """PUBLIC is a pseudo-role keyword, not an identifier; every real role name is quoted."""
    return "PUBLIC" if grantee == "PUBLIC" else ident(grantee)


def grant_statements(
    target: str,
    src_grants: Iterable[Grant],
    dst_grants: Iterable[Grant],
    src_owner: str,
    dst_owner: str,
    *,
    prefix: str = "",
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
    is security-relevant. Named-role grants are diffed only under --include-grants: they
    reference cluster-level roles that diverge across environments and fail at apply when the
    role is absent on the target, so they are opt-in, mirroring owner.

    `target` is what follows `<privilege> ON` -- the object keyword and name ("TABLE s.t",
    "SEQUENCE s.q", "SCHEMA s", "FUNCTION s.f(int)") or, for a default-privilege rule, the
    plural object type ("TABLES"). `prefix` is prepended verbatim to every statement (the
    "ALTER DEFAULT PRIVILEGES ... " clause of a default-privilege rule).
    Statements are ordered revokes-then-grants, each by (grantee, privilege), for determinism.
    """
    src_by_key = {(g.grantee, g.privilege): g for g in src_grants if g.grantee != src_owner}
    dst_by_key = {(g.grantee, g.privilege): g for g in dst_grants if g.grantee != dst_owner}

    revokes: list[str] = []
    grants: list[str] = []
    for grantee, privilege in sorted(src_by_key.keys() | dst_by_key.keys()):
        # PUBLIC is always reconciled; named roles only when opted in.
        if grantee != "PUBLIC" and not context.include_grants:
            continue
        src = src_by_key.get((grantee, privilege))
        dst = dst_by_key.get((grantee, privilege))
        on = f"{privilege} ON {target}"
        who = _render_grantee(grantee)
        if dst is None:
            revokes.append(f"{prefix}REVOKE {on} FROM {who};")
        elif src is None:
            option = " WITH GRANT OPTION" if dst.grantable else ""
            grants.append(f"{prefix}GRANT {on} TO {who}{option};")
        elif src.grantable and not dst.grantable:
            revokes.append(f"{prefix}REVOKE GRANT OPTION FOR {on} FROM {who};")
        elif dst.grantable and not src.grantable:
            grants.append(f"{prefix}GRANT {on} TO {who} WITH GRANT OPTION;")
    return revokes + grants


class _Owned(Protocol):
    """
    Any object carrying an owner and an effective ACL. Declared as read-only properties so
    plain (frozen) dataclass attributes satisfy it.
    """

    @property
    def owner(self) -> str: ...

    @property
    def grants(self) -> frozenset[Grant]: ...


def owner_and_grant_statements(
    kind: str, qualified_name: str, src_obj: _Owned | None, dst_obj: _Owned, *, phase: Phase
) -> Iterator[Statement]:
    """
    Reconcile an object's owner (ALTER <kind> ... OWNER TO, in `phase`) and its ACL
    (GRANT/REVOKE, in the GRANT phase, after every object exists) from source to target.

    Only an object present on both sides is reconciled: `src_obj` is None for one created this
    run, which -- owned by the migration runner and carrying its default ACL -- converges on a
    later run, once it exists on both sides. `kind` is both the ALTER and the GRANT object
    keyword (TABLE, SEQUENCE, SCHEMA, FUNCTION, PROCEDURE).
    """
    if src_obj is None:
        return
    for sql in owner_statements(kind, qualified_name, src_obj.owner, dst_obj.owner):
        yield Statement(phase, sql)
    for sql in grant_statements(
        f"{kind} {qualified_name}", src_obj.grants, dst_obj.grants, src_obj.owner, dst_obj.owner
    ):
        yield Statement(Phase.GRANT, sql)
