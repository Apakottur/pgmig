from tests._api.generate_setup import GenerateSetup
from tests._api.ownership import ensure_role


async def test_schema_named_grant_added(gen_setup: GenerateSetup) -> None:
    """
    With include_grants, a schema privilege on the target but not the source -> GRANT.
    """
    role = await ensure_role(gen_setup, "pgmig_grant_r")
    await gen_setup.assert_diff(
        both=["CREATE SCHEMA s"],
        src=[],
        dst=[f"GRANT CREATE ON SCHEMA s TO {role}"],
        diff=[f'GRANT CREATE ON SCHEMA "s" TO "{role}"'],
        include_grants=True,
    )
