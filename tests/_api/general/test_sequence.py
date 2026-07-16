from tests._api.generate_setup import GenerateSetup


async def test_sequence_create(gen_setup: GenerateSetup) -> None:
    """
    Sequence present in target but missing in source -> CREATE SEQUENCE.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE SEQUENCE counter AS integer INCREMENT BY 2 MINVALUE 0 MAXVALUE 100 START WITH 5 CACHE 1 CYCLE"],
        diff=[
            'CREATE SEQUENCE "public"."counter" AS integer INCREMENT BY 2 MINVALUE 0 MAXVALUE 100 START WITH 5 CACHE 1 CYCLE'
        ],
    )


async def test_sequence_create_no_cycle(gen_setup: GenerateSetup) -> None:
    """
    A non-cycling sequence is created without a trailing CYCLE.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE SEQUENCE counter AS integer INCREMENT BY 1 MINVALUE 1 MAXVALUE 100 START WITH 1 CACHE 1"],
        diff=[
            'CREATE SEQUENCE "public"."counter" AS integer INCREMENT BY 1 MINVALUE 1 MAXVALUE 100 START WITH 1 CACHE 1'
        ],
    )


async def test_sequence_drop(gen_setup: GenerateSetup) -> None:
    """
    Sequence present in source but missing in target -> DROP SEQUENCE.
    """
    await gen_setup.assert_diff(
        src=["CREATE SEQUENCE counter"],
        dst=[],
        diff=['DROP SEQUENCE "public"."counter"'],
    )


async def test_sequence_alter_increment(gen_setup: GenerateSetup) -> None:
    """
    Different increment -> ALTER SEQUENCE INCREMENT BY.
    """
    await gen_setup.assert_diff(
        src=["CREATE SEQUENCE counter INCREMENT BY 1"],
        dst=["CREATE SEQUENCE counter INCREMENT BY 5"],
        diff=['ALTER SEQUENCE "public"."counter" INCREMENT BY 5'],
    )


async def test_sequence_alter_min_and_max(gen_setup: GenerateSetup) -> None:
    """
    Different min and max -> ALTER SEQUENCE MINVALUE MAXVALUE.
    """
    # Pin START equal on both so only MINVALUE/MAXVALUE differ (START defaults to MINVALUE).
    await gen_setup.assert_diff(
        src=["CREATE SEQUENCE counter MINVALUE 1 MAXVALUE 100 START WITH 10"],
        dst=["CREATE SEQUENCE counter MINVALUE 10 MAXVALUE 200 START WITH 10"],
        diff=['ALTER SEQUENCE "public"."counter" MINVALUE 10 MAXVALUE 200'],
    )


async def test_sequence_alter_start(gen_setup: GenerateSetup) -> None:
    """
    Different start -> ALTER SEQUENCE START WITH.
    """
    await gen_setup.assert_diff(
        src=["CREATE SEQUENCE counter START WITH 1"],
        dst=["CREATE SEQUENCE counter START WITH 50"],
        diff=['ALTER SEQUENCE "public"."counter" START WITH 50'],
    )


async def test_sequence_alter_cache(gen_setup: GenerateSetup) -> None:
    """
    Different cache -> ALTER SEQUENCE CACHE.
    """
    await gen_setup.assert_diff(
        src=["CREATE SEQUENCE counter CACHE 1"],
        dst=["CREATE SEQUENCE counter CACHE 10"],
        diff=['ALTER SEQUENCE "public"."counter" CACHE 10'],
    )


async def test_sequence_toggle_cycle(gen_setup: GenerateSetup) -> None:
    """
    Cycle turned on -> ALTER SEQUENCE CYCLE; turned off -> NO CYCLE.
    """
    await gen_setup.assert_diff(
        src=["CREATE SEQUENCE counter NO CYCLE"],
        dst=["CREATE SEQUENCE counter CYCLE"],
        diff=['ALTER SEQUENCE "public"."counter" CYCLE'],
    )


async def test_sequence_toggle_cycle_off(gen_setup: GenerateSetup) -> None:
    """
    Cycle turned off -> ALTER SEQUENCE NO CYCLE.
    """
    await gen_setup.assert_diff(
        src=["CREATE SEQUENCE counter CYCLE"],
        dst=["CREATE SEQUENCE counter NO CYCLE"],
        diff=['ALTER SEQUENCE "public"."counter" NO CYCLE'],
    )


async def test_sequence_alter_type(gen_setup: GenerateSetup) -> None:
    """
    Different data type -> ALTER SEQUENCE AS.
    """
    await gen_setup.assert_diff(
        src=["CREATE SEQUENCE counter AS integer MAXVALUE 100"],
        dst=["CREATE SEQUENCE counter AS bigint MAXVALUE 100"],
        diff=['ALTER SEQUENCE "public"."counter" AS bigint'],
    )


async def test_sequence_alter_multiple_parameters(gen_setup: GenerateSetup) -> None:
    """
    Two parameters differ -> one ALTER SEQUENCE with both clauses, in fixed order.
    """
    await gen_setup.assert_diff(
        src=["CREATE SEQUENCE counter INCREMENT BY 1 CACHE 1"],
        dst=["CREATE SEQUENCE counter INCREMENT BY 3 CACHE 5"],
        diff=['ALTER SEQUENCE "public"."counter" INCREMENT BY 3 CACHE 5'],
    )


async def test_sequence_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical sequence on both sides -> no migration SQL.
    """
    await gen_setup.assert_diff(
        both=["CREATE SEQUENCE counter INCREMENT BY 2 START WITH 5"],
        src=[],
        dst=[],
        diff=[],
    )


async def test_sequence_comment_added(gen_setup: GenerateSetup) -> None:
    """
    Comment added to a sequence present on both sides -> COMMENT ON SEQUENCE.
    """
    await gen_setup.assert_diff(
        both=["CREATE SEQUENCE counter"],
        src=[],
        dst=["COMMENT ON SEQUENCE counter IS 'the counter'"],
        diff=['COMMENT ON SEQUENCE "public"."counter" IS \'the counter\''],
    )


async def test_owned_sequence_create(gen_setup: GenerateSetup) -> None:
    """
    A manually created sequence with OWNED BY table.column is introspected (it is not a
    serial/identity backing sequence). It is created before the table, and its OWNED BY is
    emitted after the table exists.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE SEQUENCE s AS integer INCREMENT BY 1 MINVALUE 1 MAXVALUE 100 START WITH 1 CACHE 1",
            "CREATE TABLE t (x integer)",
            "ALTER SEQUENCE s OWNED BY t.x",
        ],
        diff=[
            'CREATE SEQUENCE "public"."s" AS integer INCREMENT BY 1 MINVALUE 1 MAXVALUE 100 START WITH 1 CACHE 1',
            'CREATE TABLE "public"."t" ("x" integer)',
            'ALTER SEQUENCE "public"."s" OWNED BY "public"."t"."x"',
        ],
    )


async def test_owned_sequence_drop(gen_setup: GenerateSetup) -> None:
    """
    An owned sequence dropped while its owning table stays -> explicit DROP SEQUENCE.
    """
    await gen_setup.assert_diff(
        both=["CREATE TABLE t (x integer)"],
        src=["CREATE SEQUENCE s", "ALTER SEQUENCE s OWNED BY t.x"],
        dst=[],
        diff=['DROP SEQUENCE "public"."s"'],
    )


async def test_owned_sequence_drop_with_owning_table(gen_setup: GenerateSetup) -> None:
    """
    An owned sequence whose owning table is also dropped needs no explicit DROP SEQUENCE:
    the table's DROP TABLE cascades to the auto-owned sequence. Emitting one would fail
    with "sequence does not exist".
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE t (x integer)", "CREATE SEQUENCE s", "ALTER SEQUENCE s OWNED BY t.x"],
        dst=[],
        diff=['DROP TABLE "public"."t"'],
    )


async def test_owned_sequence_drop_with_owning_column(gen_setup: GenerateSetup) -> None:
    """
    An owned sequence whose owning column is dropped (the table stays) needs no explicit
    DROP SEQUENCE: DROP COLUMN cascades to the auto-owned sequence.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE t (x integer)", "CREATE SEQUENCE s", "ALTER SEQUENCE s OWNED BY t.x"],
        dst=["CREATE TABLE t (y integer)"],
        diff=[
            'ALTER TABLE "public"."t" DROP COLUMN "x"',
            'ALTER TABLE "public"."t" ADD COLUMN "y" integer',
        ],
    )


async def test_owned_sequence_drop_with_owning_schema(gen_setup: GenerateSetup) -> None:
    """
    An owned sequence whose owning schema is dropped needs no explicit DROP SEQUENCE:
    dropping the table (then the schema) cascades to the auto-owned sequence.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE SCHEMA foo",
            "CREATE TABLE foo.t (x integer)",
            "CREATE SEQUENCE foo.s",
            "ALTER SEQUENCE foo.s OWNED BY foo.t.x",
        ],
        dst=[],
        diff=[
            'DROP TABLE "foo"."t"',
            'DROP SCHEMA "foo"',
        ],
    )


async def test_owned_sequence_ownership_added(gen_setup: GenerateSetup) -> None:
    """
    Ownership added to a sequence present on both sides -> ALTER SEQUENCE ... OWNED BY.
    """
    await gen_setup.assert_diff(
        both=["CREATE SEQUENCE s", "CREATE TABLE t (x integer)"],
        src=[],
        dst=["ALTER SEQUENCE s OWNED BY t.x"],
        diff=['ALTER SEQUENCE "public"."s" OWNED BY "public"."t"."x"'],
    )


async def test_owned_sequence_ownership_removed(gen_setup: GenerateSetup) -> None:
    """
    Ownership removed from a sequence present on both sides -> ALTER SEQUENCE ... OWNED BY NONE.
    """
    await gen_setup.assert_diff(
        both=["CREATE SEQUENCE s", "CREATE TABLE t (x integer)"],
        src=["ALTER SEQUENCE s OWNED BY t.x"],
        dst=[],
        diff=['ALTER SEQUENCE "public"."s" OWNED BY NONE'],
    )


async def test_owned_sequence_ownership_retargeted(gen_setup: GenerateSetup) -> None:
    """
    Ownership moved to a different column -> ALTER SEQUENCE ... OWNED BY the new column.
    """
    await gen_setup.assert_diff(
        both=["CREATE SEQUENCE s", "CREATE TABLE t (a integer, b integer)"],
        src=["ALTER SEQUENCE s OWNED BY t.a"],
        dst=["ALTER SEQUENCE s OWNED BY t.b"],
        diff=['ALTER SEQUENCE "public"."s" OWNED BY "public"."t"."b"'],
    )


async def test_owned_sequence_unchanged(gen_setup: GenerateSetup) -> None:
    """
    An owned sequence identical on both sides -> no migration SQL.
    """
    await gen_setup.assert_diff(
        both=["CREATE SEQUENCE s", "CREATE TABLE t (x integer)", "ALTER SEQUENCE s OWNED BY t.x"],
        src=[],
        dst=[],
        diff=[],
    )


async def test_sequence_owned_by_identity_column_excluded(gen_setup: GenerateSetup) -> None:
    """
    A sequence auto-owned by an identity column is excluded from standalone introspection:
    an identity column manages its own sequence, and this is indistinguishable in the
    catalog from the orphan a serial->identity conversion leaves behind (an 'a'-owned
    sequence on the now-identity column). Only the identity table surfaces.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE TABLE t (id integer GENERATED BY DEFAULT AS IDENTITY)",
            "CREATE SEQUENCE s",
            "ALTER SEQUENCE s OWNED BY t.id",
        ],
        diff=['CREATE TABLE "public"."t" ("id" integer GENERATED BY DEFAULT AS IDENTITY)'],
    )


async def test_serial_backing_sequence_still_excluded(gen_setup: GenerateSetup) -> None:
    """
    A serial column's backing sequence stays excluded from standalone introspection even
    alongside a manually owned sequence: only the manual one surfaces as a CREATE SEQUENCE.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE TABLE person (id serial)",
            "CREATE SEQUENCE s",
            "ALTER SEQUENCE s OWNED BY person.id",
        ],
        diff=[
            'CREATE SEQUENCE "public"."s" AS bigint INCREMENT BY 1 MINVALUE 1 '
            "MAXVALUE 9223372036854775807 START WITH 1 CACHE 1",
            'CREATE TABLE "public"."person" ("id" serial)',
            'ALTER SEQUENCE "public"."s" OWNED BY "public"."person"."id"',
        ],
    )
