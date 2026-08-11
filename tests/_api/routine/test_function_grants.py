from tests._api.generate_setup import GenerateSetup

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
