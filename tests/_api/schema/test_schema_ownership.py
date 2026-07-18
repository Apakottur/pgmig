from tests._api.generate_setup import GenerateSetup
from tests._api.ownership import ensure_role


async def test_schema_owner_changed_with_include_owner(gen_setup: GenerateSetup) -> None:
    """
    Same schema both sides owned by different roles, with --include-owner -> ALTER SCHEMA ...
    OWNER TO target's.
    """
    role_a = await ensure_role(gen_setup, "pgmig_owner_a")
    role_b = await ensure_role(gen_setup, "pgmig_owner_b")

    await gen_setup.assert_diff(
        both=["CREATE SCHEMA s"],
        src=[f"ALTER SCHEMA s OWNER TO {role_a}"],
        dst=[f"ALTER SCHEMA s OWNER TO {role_b}"],
        diff=[f'ALTER SCHEMA "s" OWNER TO "{role_b}"'],
        include_owner=True,
    )
