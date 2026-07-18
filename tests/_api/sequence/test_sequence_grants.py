from tests._api.generate_setup import GenerateSetup
from tests._api.ownership import ensure_role


async def test_sequence_named_grant_off_by_default(gen_setup: GenerateSetup) -> None:
    """
    A named-role grant on a sequence is role-dependent, so it is NOT diffed by default.
    """
    role = await ensure_role(gen_setup, "pgmig_grant_r")
    await gen_setup.assert_diff(
        both=["CREATE SEQUENCE s"],
        src=[],
        dst=[f"GRANT USAGE ON SEQUENCE s TO {role}"],
        diff=[],
    )


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


async def test_sequence_public_grant_diffed_by_default(gen_setup: GenerateSetup) -> None:
    """
    A grant to PUBLIC on a sequence is diffed by default (no flag).
    """
    await gen_setup.assert_diff(
        both=["CREATE SEQUENCE s"],
        src=[],
        dst=["GRANT SELECT ON SEQUENCE s TO PUBLIC"],
        diff=['GRANT SELECT ON SEQUENCE "public"."s" TO PUBLIC'],
    )


async def test_sequence_grant_default_acl_no_diff(gen_setup: GenerateSetup) -> None:
    """
    A sequence with the owner-default ACL on both sides must not diff: the NULL relacl is
    compared as its acldefault('s', owner) expansion, not an empty set.
    """
    await gen_setup.assert_diff(
        src=["CREATE SEQUENCE s"],
        dst=["CREATE SEQUENCE s"],
        diff=[],
    )
