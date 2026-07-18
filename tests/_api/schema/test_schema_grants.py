from tests._api.generate_setup import GenerateSetup
from tests._api.ownership import ensure_role


async def test_schema_named_grant_off_by_default(gen_setup: GenerateSetup) -> None:
    """
    A named-role grant on a schema is role-dependent, so it is NOT diffed by default.
    """
    role = await ensure_role(gen_setup, "pgmig_grant_r")
    await gen_setup.assert_diff(
        both=["CREATE SCHEMA s"],
        src=[],
        dst=[f"GRANT USAGE ON SCHEMA s TO {role}"],
        diff=[],
    )


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


async def test_schema_public_grant_diffed_by_default(gen_setup: GenerateSetup) -> None:
    """
    A grant to PUBLIC on a schema is diffed by default (no flag).
    """
    await gen_setup.assert_diff(
        both=["CREATE SCHEMA s"],
        src=[],
        dst=["GRANT USAGE ON SCHEMA s TO PUBLIC"],
        diff=['GRANT USAGE ON SCHEMA "s" TO PUBLIC'],
    )


async def test_schema_grant_default_acl_no_diff(gen_setup: GenerateSetup) -> None:
    """
    A schema with the owner-default ACL on both sides must not diff: the NULL nspacl is
    compared as its acldefault('n', owner) expansion, not an empty set.
    """
    await gen_setup.assert_diff(
        src=["CREATE SCHEMA s"],
        dst=["CREATE SCHEMA s"],
        diff=[],
    )
