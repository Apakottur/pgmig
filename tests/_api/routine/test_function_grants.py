from tests._api.generate_setup import GenerateSetup
from tests._api.ownership import ensure_role

_FUNC = "CREATE FUNCTION f() RETURNS integer LANGUAGE sql AS 'SELECT 1'"
_PROC = "CREATE PROCEDURE p() LANGUAGE sql AS ''"


async def test_function_revoke_execute_from_public(gen_setup: GenerateSetup) -> None:
    """
    A function's default ACL grants EXECUTE to PUBLIC. Revoking it on the target only -> REVOKE
    EXECUTE ... FROM PUBLIC, diffed by default (no flag). This is the security-relevant case.
    """
    await gen_setup.assert_diff(
        both=[_FUNC],
        src=[],
        dst=["REVOKE EXECUTE ON FUNCTION f() FROM PUBLIC"],
        diff=['REVOKE EXECUTE ON FUNCTION "public"."f"() FROM PUBLIC'],
    )


async def test_procedure_revoke_execute_from_public(gen_setup: GenerateSetup) -> None:
    """
    A procedure's default ACL grants EXECUTE to PUBLIC; the object keyword is ON PROCEDURE.
    """
    await gen_setup.assert_diff(
        both=[_PROC],
        src=[],
        dst=["REVOKE EXECUTE ON PROCEDURE p() FROM PUBLIC"],
        diff=['REVOKE EXECUTE ON PROCEDURE "public"."p"() FROM PUBLIC'],
    )


async def test_function_named_grant_off_by_default(gen_setup: GenerateSetup) -> None:
    """
    A named-role EXECUTE grant is role-dependent, so it is NOT diffed by default.
    """
    role = await ensure_role(gen_setup, "pgmig_grant_r")
    await gen_setup.assert_diff(
        both=[_FUNC],
        src=[],
        dst=[f"GRANT EXECUTE ON FUNCTION f() TO {role}"],
        diff=[],
    )


async def test_function_named_grant_added(gen_setup: GenerateSetup) -> None:
    """
    With include_grants, an EXECUTE grant to a named role on the target only -> GRANT.
    """
    role = await ensure_role(gen_setup, "pgmig_grant_r")
    await gen_setup.assert_diff(
        both=[_FUNC],
        src=[],
        dst=[f"GRANT EXECUTE ON FUNCTION f() TO {role}"],
        diff=[f'GRANT EXECUTE ON FUNCTION "public"."f"() TO "{role}"'],
        include_grants=True,
    )


async def test_function_grant_default_acl_no_diff(gen_setup: GenerateSetup) -> None:
    """
    A function with the owner-default ACL on both sides must not diff: the NULL proacl is
    compared as its acldefault('f', owner) expansion (PUBLIC EXECUTE), not an empty set.
    """
    await gen_setup.assert_diff(
        src=[_FUNC],
        dst=[_FUNC],
        diff=[],
    )
