from tests._api.generate_setup import GenerateSetup


async def test_replica_identity_default_to_full(gen_setup: GenerateSetup) -> None:
    """
    A table at the default replica identity in source and FULL in target -> ALTER TABLE
    ... REPLICA IDENTITY FULL.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE t (id integer)"],
        dst=[
            "CREATE TABLE t (id integer)",
            "ALTER TABLE t REPLICA IDENTITY FULL",
        ],
        diff=['ALTER TABLE "public"."t" REPLICA IDENTITY FULL'],
    )


async def test_replica_identity_full_to_default(gen_setup: GenerateSetup) -> None:
    """
    FULL in source, default in target -> ALTER TABLE ... REPLICA IDENTITY DEFAULT.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE t (id integer)",
            "ALTER TABLE t REPLICA IDENTITY FULL",
        ],
        dst=["CREATE TABLE t (id integer)"],
        diff=['ALTER TABLE "public"."t" REPLICA IDENTITY DEFAULT'],
    )


async def test_replica_identity_default_to_nothing(gen_setup: GenerateSetup) -> None:
    """
    Default in source, NOTHING in target -> ALTER TABLE ... REPLICA IDENTITY NOTHING.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE t (id integer)"],
        dst=[
            "CREATE TABLE t (id integer)",
            "ALTER TABLE t REPLICA IDENTITY NOTHING",
        ],
        diff=['ALTER TABLE "public"."t" REPLICA IDENTITY NOTHING'],
    )


async def test_replica_identity_using_index_set(gen_setup: GenerateSetup) -> None:
    """
    An existing unique index becomes the replica identity in target only -> ALTER TABLE
    ... REPLICA IDENTITY USING INDEX. The index exists on both sides, so only the identity
    ALTER is emitted.
    """
    await gen_setup.assert_diff(
        both=[
            "CREATE TABLE t (id integer NOT NULL)",
            "CREATE UNIQUE INDEX t_uidx ON t (id)",
        ],
        src=[],
        dst=["ALTER TABLE t REPLICA IDENTITY USING INDEX t_uidx"],
        diff=['ALTER TABLE "public"."t" REPLICA IDENTITY USING INDEX "t_uidx"'],
    )


async def test_replica_identity_using_index_changed(gen_setup: GenerateSetup) -> None:
    """
    The replica identity index differs between sides (both indexes exist on both sides) ->
    ALTER TABLE ... REPLICA IDENTITY USING INDEX <target index>.
    """
    await gen_setup.assert_diff(
        both=[
            "CREATE TABLE t (a integer NOT NULL, b integer NOT NULL)",
            "CREATE UNIQUE INDEX t_a_idx ON t (a)",
            "CREATE UNIQUE INDEX t_b_idx ON t (b)",
        ],
        src=["ALTER TABLE t REPLICA IDENTITY USING INDEX t_a_idx"],
        dst=["ALTER TABLE t REPLICA IDENTITY USING INDEX t_b_idx"],
        diff=['ALTER TABLE "public"."t" REPLICA IDENTITY USING INDEX "t_b_idx"'],
    )


async def test_replica_identity_using_index_dropped_back(gen_setup: GenerateSetup) -> None:
    """
    Source uses a unique index as replica identity; target is back at the default (the
    index still exists, just no longer the identity) -> ALTER TABLE ... REPLICA IDENTITY
    DEFAULT.
    """
    await gen_setup.assert_diff(
        both=[
            "CREATE TABLE t (id integer NOT NULL)",
            "CREATE UNIQUE INDEX t_uidx ON t (id)",
        ],
        src=["ALTER TABLE t REPLICA IDENTITY USING INDEX t_uidx"],
        dst=[],
        diff=['ALTER TABLE "public"."t" REPLICA IDENTITY DEFAULT'],
    )


async def test_replica_identity_create_table_full(gen_setup: GenerateSetup) -> None:
    """
    A new table with a non-default replica identity -> CREATE TABLE then, in a later phase,
    the REPLICA IDENTITY ALTER.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE TABLE t (id integer)",
            "ALTER TABLE t REPLICA IDENTITY FULL",
        ],
        diff=[
            'CREATE TABLE "public"."t" ("id" integer)',
            'ALTER TABLE "public"."t" REPLICA IDENTITY FULL',
        ],
    )


async def test_replica_identity_create_table_using_index(gen_setup: GenerateSetup) -> None:
    """
    A new table whose replica identity is a unique index -> CREATE TABLE, then the index,
    then the REPLICA IDENTITY USING INDEX ALTER, in that phase order (the ALTER references
    the index by name, so it must land after the index is created).
    """
    await gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE TABLE t (id integer NOT NULL)",
            "CREATE UNIQUE INDEX t_uidx ON t (id)",
            "ALTER TABLE t REPLICA IDENTITY USING INDEX t_uidx",
        ],
        diff=[
            'CREATE TABLE "public"."t" ("id" integer NOT NULL)',
            "CREATE UNIQUE INDEX t_uidx ON public.t USING btree (id)",
            'ALTER TABLE "public"."t" REPLICA IDENTITY USING INDEX "t_uidx"',
        ],
    )


async def test_replica_identity_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Same replica identity on both sides -> no migration SQL.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE t (id integer)",
            "ALTER TABLE t REPLICA IDENTITY FULL",
        ],
        dst=[
            "CREATE TABLE t (id integer)",
            "ALTER TABLE t REPLICA IDENTITY FULL",
        ],
        diff=[],
    )
