from tests._api.generate_setup import GenerateSetup


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
