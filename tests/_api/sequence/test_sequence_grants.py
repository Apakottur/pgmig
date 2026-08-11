from tests._api.generate_setup import GenerateSetup
from tests._api.ownership import ensure_role


async def test_sequence_named_grant_added(gen_setup: GenerateSetup) -> None:
    """
    With include_grants, a sequence privilege on the target but not the source -> GRANT.
    """
    role = await ensure_role(gen_setup, "pgmig_grant_r")
    await gen_setup.assert_diff(
        both=["CREATE SEQUENCE s"],
        src=[],
        dst=[f"GRANT USAGE ON SEQUENCE s TO {role}"],
        diff=[f'GRANT USAGE ON SEQUENCE "public"."s" TO "{role}"'],
        include_grants=True,
    )


async def test_sequence_named_grant_removed(gen_setup: GenerateSetup) -> None:
    """
    With include_grants, a sequence privilege on the source but not the target -> REVOKE.
    """
    role = await ensure_role(gen_setup, "pgmig_grant_r")
    await gen_setup.assert_diff(
        both=["CREATE SEQUENCE s"],
        src=[f"GRANT UPDATE ON SEQUENCE s TO {role}"],
        dst=[],
        diff=[f'REVOKE UPDATE ON SEQUENCE "public"."s" FROM "{role}"'],
        include_grants=True,
    )
