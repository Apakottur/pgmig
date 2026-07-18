from tests._api.generate_setup import GenerateSetup
from tests._api.ownership import ensure_role


async def test_function_owner_changed_with_include_owner(gen_setup: GenerateSetup) -> None:
    """
    Same function both sides owned by different roles, with --include-owner -> ALTER FUNCTION
    ... OWNER TO target's.
    """
    role_a = await ensure_role(gen_setup, "pgmig_owner_a")
    role_b = await ensure_role(gen_setup, "pgmig_owner_b")

    await gen_setup.assert_diff(
        both=["CREATE FUNCTION f() RETURNS integer LANGUAGE sql AS 'SELECT 1'"],
        src=[f"ALTER FUNCTION f() OWNER TO {role_a}"],
        dst=[f"ALTER FUNCTION f() OWNER TO {role_b}"],
        diff=[f'ALTER FUNCTION "public"."f"() OWNER TO "{role_b}"'],
        include_owner=True,
    )


async def test_procedure_owner_changed_with_include_owner(gen_setup: GenerateSetup) -> None:
    """
    Same procedure both sides owned by different roles, with --include-owner -> ALTER PROCEDURE
    ... OWNER TO target's (the ALTER keyword follows prokind, distinct from a function).
    """
    role_a = await ensure_role(gen_setup, "pgmig_owner_a")
    role_b = await ensure_role(gen_setup, "pgmig_owner_b")

    await gen_setup.assert_diff(
        both=["CREATE PROCEDURE p() LANGUAGE sql AS ''"],
        src=[f"ALTER PROCEDURE p() OWNER TO {role_a}"],
        dst=[f"ALTER PROCEDURE p() OWNER TO {role_b}"],
        diff=[f'ALTER PROCEDURE "public"."p"() OWNER TO "{role_b}"'],
        include_owner=True,
    )
