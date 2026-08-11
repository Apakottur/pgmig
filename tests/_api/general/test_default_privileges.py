from tests._api.generate_setup import GenerateSetup
from tests._api.ownership import ensure_role


async def test_default_priv_named_grant_off_by_default(gen_setup: GenerateSetup) -> None:
    """
    A default-privilege rule granting to a named role is role-dependent, so it is NOT diffed by
    default (no flag, no statement).
    """
    owner = await ensure_role(gen_setup, "pgmig_dp_owner")
    grantee = await ensure_role(gen_setup, "pgmig_dp_grantee")
    await gen_setup.assert_diff(
        src=[],
        dst=[f"ALTER DEFAULT PRIVILEGES FOR ROLE {owner} GRANT SELECT ON TABLES TO {grantee}"],
        diff=[],
    )


async def test_default_priv_named_grant_added(gen_setup: GenerateSetup) -> None:
    """
    With include_grants, a default-privilege GRANT present on the target but not the source ->
    ALTER DEFAULT PRIVILEGES ... GRANT.
    """
    owner = await ensure_role(gen_setup, "pgmig_dp_owner")
    grantee = await ensure_role(gen_setup, "pgmig_dp_grantee")
    await gen_setup.assert_diff(
        src=[],
        dst=[f"ALTER DEFAULT PRIVILEGES FOR ROLE {owner} GRANT SELECT ON TABLES TO {grantee}"],
        diff=[f'ALTER DEFAULT PRIVILEGES FOR ROLE "{owner}" GRANT SELECT ON TABLES TO "{grantee}"'],
        include_grants=True,
    )


async def test_default_priv_named_grant_removed(gen_setup: GenerateSetup) -> None:
    """
    With include_grants, a rule present only on the source -> REVOKE (undo the configured grant,
    returning the source to the built-in default the target has).
    """
    owner = await ensure_role(gen_setup, "pgmig_dp_owner")
    grantee = await ensure_role(gen_setup, "pgmig_dp_grantee")
    await gen_setup.assert_diff(
        src=[f"ALTER DEFAULT PRIVILEGES FOR ROLE {owner} GRANT SELECT ON TABLES TO {grantee}"],
        dst=[],
        diff=[f'ALTER DEFAULT PRIVILEGES FOR ROLE "{owner}" REVOKE SELECT ON TABLES FROM "{grantee}"'],
        include_grants=True,
    )


async def test_default_priv_in_schema(gen_setup: GenerateSetup) -> None:
    """
    A schema-scoped rule renders the IN SCHEMA clause.
    """
    owner = await ensure_role(gen_setup, "pgmig_dp_owner")
    grantee = await ensure_role(gen_setup, "pgmig_dp_grantee")
    await gen_setup.assert_diff(
        both=["CREATE SCHEMA s"],
        src=[],
        dst=[f"ALTER DEFAULT PRIVILEGES FOR ROLE {owner} IN SCHEMA s GRANT USAGE ON SEQUENCES TO {grantee}"],
        diff=[f'ALTER DEFAULT PRIVILEGES FOR ROLE "{owner}" IN SCHEMA "s" GRANT USAGE ON SEQUENCES TO "{grantee}"'],
        include_grants=True,
    )


async def test_default_priv_grant_option_added(gen_setup: GenerateSetup) -> None:
    """
    With include_grants, adding WITH GRANT OPTION to an existing default-privilege grant ->
    GRANT ... WITH GRANT OPTION (not a full revoke-then-grant).
    """
    owner = await ensure_role(gen_setup, "pgmig_dp_owner")
    grantee = await ensure_role(gen_setup, "pgmig_dp_grantee")
    await gen_setup.assert_diff(
        src=[f"ALTER DEFAULT PRIVILEGES FOR ROLE {owner} GRANT SELECT ON TABLES TO {grantee}"],
        dst=[f"ALTER DEFAULT PRIVILEGES FOR ROLE {owner} GRANT SELECT ON TABLES TO {grantee} WITH GRANT OPTION"],
        diff=[f'ALTER DEFAULT PRIVILEGES FOR ROLE "{owner}" GRANT SELECT ON TABLES TO "{grantee}" WITH GRANT OPTION'],
        include_grants=True,
    )


async def test_default_priv_grant_option_removed(gen_setup: GenerateSetup) -> None:
    """
    With include_grants, removing only the grant option (privilege kept) -> REVOKE GRANT OPTION
    FOR, not a full revoke-then-grant.
    """
    owner = await ensure_role(gen_setup, "pgmig_dp_owner")
    grantee = await ensure_role(gen_setup, "pgmig_dp_grantee")
    await gen_setup.assert_diff(
        src=[f"ALTER DEFAULT PRIVILEGES FOR ROLE {owner} GRANT SELECT ON TABLES TO {grantee} WITH GRANT OPTION"],
        dst=[f"ALTER DEFAULT PRIVILEGES FOR ROLE {owner} GRANT SELECT ON TABLES TO {grantee}"],
        diff=[f'ALTER DEFAULT PRIVILEGES FOR ROLE "{owner}" REVOKE GRANT OPTION FOR SELECT ON TABLES FROM "{grantee}"'],
        include_grants=True,
    )


async def test_default_priv_public_grant_diffed_by_default(gen_setup: GenerateSetup) -> None:
    """
    A default-privilege grant to PUBLIC is diffed by default (no flag) -- portable and
    security-relevant, like object-level PUBLIC grants.
    """
    owner = await ensure_role(gen_setup, "pgmig_dp_owner")
    await gen_setup.assert_diff(
        src=[],
        dst=[f"ALTER DEFAULT PRIVILEGES FOR ROLE {owner} GRANT SELECT ON TABLES TO PUBLIC"],
        diff=[f'ALTER DEFAULT PRIVILEGES FOR ROLE "{owner}" GRANT SELECT ON TABLES TO PUBLIC'],
    )


async def test_default_priv_function_revoke_execute_from_public(gen_setup: GenerateSetup) -> None:
    """
    The built-in default grants EXECUTE on FUNCTIONS to PUBLIC. A rule that revokes it on the
    target only -> REVOKE EXECUTE ... FROM PUBLIC, diffed by default. This is the
    security-relevant case, and exercises the baseline expansion: the source has no row, so its
    effective default is the built-in (PUBLIC EXECUTE), which the target's rule removes.
    """
    owner = await ensure_role(gen_setup, "pgmig_dp_owner")
    await gen_setup.assert_diff(
        src=[],
        dst=[f"ALTER DEFAULT PRIVILEGES FOR ROLE {owner} REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC"],
        diff=[f'ALTER DEFAULT PRIVILEGES FOR ROLE "{owner}" REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC'],
    )


async def test_default_priv_no_diff(gen_setup: GenerateSetup) -> None:
    """
    Identical default-privilege configuration on both sides -> no migration SQL, even with
    include_grants.
    """
    owner = await ensure_role(gen_setup, "pgmig_dp_owner")
    grantee = await ensure_role(gen_setup, "pgmig_dp_grantee")
    rule = f"ALTER DEFAULT PRIVILEGES FOR ROLE {owner} GRANT SELECT ON TABLES TO {grantee}"
    await gen_setup.assert_diff(
        src=[rule],
        dst=[rule],
        diff=[],
        include_grants=True,
    )


async def test_default_priv_none_configured_no_diff(gen_setup: GenerateSetup) -> None:
    """
    No default-privilege rules on either side (built-in defaults everywhere) -> no diff. Guards
    against the baseline expansion spuriously emitting statements when neither side has a row.
    """
    await gen_setup.assert_diff(src=[], dst=[], diff=[], include_grants=True)
