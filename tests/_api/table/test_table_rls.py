from tests._api.generate_setup import GenerateSetup


async def test_create_table_with_rls_enabled(gen_setup: GenerateSetup) -> None:
    """
    A new table with row-level security enabled: CREATE TABLE has no inline RLS syntax, so a
    following ALTER TABLE ... ENABLE ROW LEVEL SECURITY must be emitted.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE TABLE t (id integer)", "ALTER TABLE t ENABLE ROW LEVEL SECURITY"],
        diff=[
            'CREATE TABLE "public"."t" ("id" integer)',
            'ALTER TABLE "public"."t" ENABLE ROW LEVEL SECURITY',
        ],
    )


async def test_enable_rls(gen_setup: GenerateSetup) -> None:
    """
    Same table, RLS off in source and on in target -> ALTER TABLE ... ENABLE ROW LEVEL SECURITY.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE t (id integer)"],
        dst=["CREATE TABLE t (id integer)", "ALTER TABLE t ENABLE ROW LEVEL SECURITY"],
        diff=['ALTER TABLE "public"."t" ENABLE ROW LEVEL SECURITY'],
    )


async def test_disable_rls(gen_setup: GenerateSetup) -> None:
    """
    Same table, RLS on in source and off in target -> ALTER TABLE ... DISABLE ROW LEVEL SECURITY.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE t (id integer)", "ALTER TABLE t ENABLE ROW LEVEL SECURITY"],
        dst=["CREATE TABLE t (id integer)"],
        diff=['ALTER TABLE "public"."t" DISABLE ROW LEVEL SECURITY'],
    )


async def test_force_rls(gen_setup: GenerateSetup) -> None:
    """
    RLS enabled on both sides, forced only on target -> ALTER TABLE ... FORCE ROW LEVEL SECURITY.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE t (id integer)", "ALTER TABLE t ENABLE ROW LEVEL SECURITY"],
        dst=[
            "CREATE TABLE t (id integer)",
            "ALTER TABLE t ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE t FORCE ROW LEVEL SECURITY",
        ],
        diff=['ALTER TABLE "public"."t" FORCE ROW LEVEL SECURITY'],
    )


async def test_no_force_rls(gen_setup: GenerateSetup) -> None:
    """
    RLS enabled on both sides, forced only on source -> ALTER TABLE ... NO FORCE ROW LEVEL SECURITY.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE t (id integer)",
            "ALTER TABLE t ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE t FORCE ROW LEVEL SECURITY",
        ],
        dst=["CREATE TABLE t (id integer)", "ALTER TABLE t ENABLE ROW LEVEL SECURITY"],
        diff=['ALTER TABLE "public"."t" NO FORCE ROW LEVEL SECURITY'],
    )


async def test_enable_and_force_together(gen_setup: GenerateSetup) -> None:
    """
    Both flags flip on at once: ENABLE precedes FORCE.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE t (id integer)"],
        dst=[
            "CREATE TABLE t (id integer)",
            "ALTER TABLE t ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE t FORCE ROW LEVEL SECURITY",
        ],
        diff=[
            'ALTER TABLE "public"."t" ENABLE ROW LEVEL SECURITY',
            'ALTER TABLE "public"."t" FORCE ROW LEVEL SECURITY',
        ],
    )


async def test_rls_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Same RLS state on both sides -> no migration SQL.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE t (id integer)", "ALTER TABLE t ENABLE ROW LEVEL SECURITY"],
        dst=["CREATE TABLE t (id integer)", "ALTER TABLE t ENABLE ROW LEVEL SECURITY"],
        diff=[],
    )
