from tests._api.generate_setup import GenerateSetup
from tests._api.ownership import ensure_role


async def test_sequence_owner_changed_with_include_owner(gen_setup: GenerateSetup) -> None:
    """
    Same sequence both sides owned by different roles, with --include-owner -> ALTER SEQUENCE
    ... OWNER TO target's.
    """
    role_a = await ensure_role(gen_setup, "pgmig_owner_a")
    role_b = await ensure_role(gen_setup, "pgmig_owner_b")

    await gen_setup.assert_diff(
        both=["CREATE SEQUENCE s"],
        src=[f"ALTER SEQUENCE s OWNER TO {role_a}"],
        dst=[f"ALTER SEQUENCE s OWNER TO {role_b}"],
        diff=[f'ALTER SEQUENCE "public"."s" OWNER TO "{role_b}"'],
        include_owner=True,
    )


async def test_sequence_owner_ignored_by_default(gen_setup: GenerateSetup) -> None:
    """
    Owners differ, but ownership is not reconciled by default (no --include-owner).
    """
    role_a = await ensure_role(gen_setup, "pgmig_owner_a")
    role_b = await ensure_role(gen_setup, "pgmig_owner_b")

    await gen_setup.assert_diff(
        both=["CREATE SEQUENCE s"],
        src=[f"ALTER SEQUENCE s OWNER TO {role_a}"],
        dst=[f"ALTER SEQUENCE s OWNER TO {role_b}"],
        diff=[],
    )
