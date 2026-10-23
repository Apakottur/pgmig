from tests._api.generate_setup import GenerateSetup
from tests._api.ownership import ensure_role

# --- Named-role grants: opt-in behind include_grants ---


async def test_table_named_grant_off_by_default(gen_setup: GenerateSetup) -> None:
    """
    A named-role grant is role-dependent (may fail at apply on a cluster missing the role), so
    it is NOT diffed by default -- no flag, no statement.
    """
    role = await ensure_role(gen_setup, "pgmig_grant_r")
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (name text)"],
        dst=["CREATE TABLE person (name text)", f"GRANT SELECT ON person TO {role}"],
        diff=[],
    )


async def test_table_grant_added(gen_setup: GenerateSetup) -> None:
    """
    With include_grants, a privilege granted on the target but not the source -> GRANT.
    """
    role = await ensure_role(gen_setup, "pgmig_grant_r")
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (name text)"],
        dst=["CREATE TABLE person (name text)", f"GRANT SELECT ON person TO {role}"],
        diff=[f'GRANT SELECT ON TABLE "public"."person" TO "{role}"'],
        include_grants=True,
    )


async def test_table_grant_removed(gen_setup: GenerateSetup) -> None:
    """
    With include_grants, a privilege granted on the source but not the target -> REVOKE.
    """
    role = await ensure_role(gen_setup, "pgmig_grant_r")
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (name text)", f"GRANT SELECT ON person TO {role}"],
        dst=["CREATE TABLE person (name text)"],
        diff=[f'REVOKE SELECT ON TABLE "public"."person" FROM "{role}"'],
        include_grants=True,
    )


async def test_table_grant_option_added(gen_setup: GenerateSetup) -> None:
    """
    With include_grants, adding WITH GRANT OPTION to an existing privilege -> GRANT ... WITH
    GRANT OPTION.
    """
    role = await ensure_role(gen_setup, "pgmig_grant_r")
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (name text)", f"GRANT SELECT ON person TO {role}"],
        dst=["CREATE TABLE person (name text)", f"GRANT SELECT ON person TO {role} WITH GRANT OPTION"],
        diff=[f'GRANT SELECT ON TABLE "public"."person" TO "{role}" WITH GRANT OPTION'],
        include_grants=True,
    )


async def test_table_grant_option_removed(gen_setup: GenerateSetup) -> None:
    """
    With include_grants, removing only the grant option (privilege kept) -> REVOKE GRANT OPTION
    FOR, not a full revoke-then-grant.
    """
    role = await ensure_role(gen_setup, "pgmig_grant_r")
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (name text)", f"GRANT SELECT ON person TO {role} WITH GRANT OPTION"],
        dst=["CREATE TABLE person (name text)", f"GRANT SELECT ON person TO {role}"],
        diff=[f'REVOKE GRANT OPTION FOR SELECT ON TABLE "public"."person" FROM "{role}"'],
        include_grants=True,
    )


async def test_table_grant_multiple_ordered(gen_setup: GenerateSetup) -> None:
    """
    With include_grants, multiple privileges and grantees are emitted deterministically, sorted
    by (grantee, privilege).
    """
    role_a = await ensure_role(gen_setup, "pgmig_grant_a")
    role_b = await ensure_role(gen_setup, "pgmig_grant_b")
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (name text)"],
        dst=[
            "CREATE TABLE person (name text)",
            f"GRANT INSERT, SELECT ON person TO {role_a}",
            f"GRANT SELECT ON person TO {role_b}",
        ],
        diff=[
            f'GRANT INSERT ON TABLE "public"."person" TO "{role_a}"',
            f'GRANT SELECT ON TABLE "public"."person" TO "{role_a}"',
            f'GRANT SELECT ON TABLE "public"."person" TO "{role_b}"',
        ],
        include_grants=True,
    )


# --- PUBLIC grants: always diffed (portable, apply-safe, security-relevant) ---


async def test_table_public_grant_diffed_by_default(gen_setup: GenerateSetup) -> None:
    """
    A grant to PUBLIC is diffed by default (no flag) and renders as the bare PUBLIC keyword.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (name text)"],
        dst=["CREATE TABLE person (name text)", "GRANT SELECT ON person TO PUBLIC"],
        diff=['GRANT SELECT ON TABLE "public"."person" TO PUBLIC'],
    )


async def test_table_public_revoke_diffed_by_default(gen_setup: GenerateSetup) -> None:
    """
    A PUBLIC grant present only in the source is revoked by default -- catches drift like a
    missing REVOKE ... FROM PUBLIC.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (name text)", "GRANT SELECT ON person TO PUBLIC"],
        dst=["CREATE TABLE person (name text)"],
        diff=['REVOKE SELECT ON TABLE "public"."person" FROM PUBLIC'],
    )


async def test_table_public_diffed_named_skipped_by_default(gen_setup: GenerateSetup) -> None:
    """
    The Option B split: with no flag, a PUBLIC grant IS emitted while a named-role grant added
    alongside it is NOT.
    """
    role = await ensure_role(gen_setup, "pgmig_grant_r")
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (name text)"],
        dst=[
            "CREATE TABLE person (name text)",
            f"GRANT SELECT ON person TO {role}",
            "GRANT SELECT ON person TO PUBLIC",
        ],
        diff=['GRANT SELECT ON TABLE "public"."person" TO PUBLIC'],
    )


async def test_table_public_and_named_both_with_flag(gen_setup: GenerateSetup) -> None:
    """
    With include_grants, both the PUBLIC and the named-role grant are emitted (ordered by grantee).
    """
    role = await ensure_role(gen_setup, "pgmig_grant_r")
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (name text)"],
        dst=[
            "CREATE TABLE person (name text)",
            f"GRANT SELECT ON person TO {role}",
            "GRANT SELECT ON person TO PUBLIC",
        ],
        diff=[
            'GRANT SELECT ON TABLE "public"."person" TO PUBLIC',
            f'GRANT SELECT ON TABLE "public"."person" TO "{role}"',
        ],
        include_grants=True,
    )


async def test_table_grant_default_acl_no_diff(gen_setup: GenerateSetup) -> None:
    """
    A plain table with the owner-default ACL on both sides must not diff: the NULL relacl is
    compared as its acldefault expansion, not an empty set.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (name text)"],
        dst=["CREATE TABLE person (name text)"],
        diff=[],
    )
