from tests._api.generate_setup import GenerateSetup


async def test_range_type_create(gen_setup: GenerateSetup) -> None:
    """
    Range type present in target but missing in source -> CREATE TYPE ... AS RANGE.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE TYPE r_int AS RANGE (subtype = integer)"],
        diff=['CREATE TYPE "public"."r_int" AS RANGE (SUBTYPE = integer)'],
    )


async def test_range_type_create_with_subtype_diff(gen_setup: GenerateSetup) -> None:
    """
    A SUBTYPE_DIFF function is carried into the CREATE clause.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE TYPE r_float AS RANGE (subtype = float8, subtype_diff = float8mi)"],
        diff=['CREATE TYPE "public"."r_float" AS RANGE (SUBTYPE = double precision, SUBTYPE_DIFF = float8mi)'],
    )


async def test_range_type_create_with_collation(gen_setup: GenerateSetup) -> None:
    """
    An explicit, non-default COLLATION on a collatable subtype is carried into the CREATE clause.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=['CREATE TYPE r_text AS RANGE (subtype = text, collation = "C")'],
        diff=['CREATE TYPE "public"."r_text" AS RANGE (SUBTYPE = text, COLLATION = pg_catalog."C")'],
    )


async def test_range_type_over_user_enum_created_after_enum(gen_setup: GenerateSetup) -> None:
    """
    A range over a user enum must be created after the enum it ranges over. The enum generator
    runs before the range generator and both emit in the same phase, so the enum's CREATE
    precedes the range's regardless of name order.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE TYPE mood AS ENUM ('sad', 'ok', 'glad')",
            "CREATE TYPE r_mood AS RANGE (subtype = mood)",
        ],
        diff=[
            "CREATE TYPE \"public\".\"mood\" AS ENUM ('sad', 'ok', 'glad')",
            'CREATE TYPE "public"."r_mood" AS RANGE (SUBTYPE = public.mood)',
        ],
    )


async def test_range_type_drop(gen_setup: GenerateSetup) -> None:
    """
    Range type present in source but missing in target -> DROP TYPE.
    """
    await gen_setup.assert_diff(
        src=["CREATE TYPE r_int AS RANGE (subtype = integer)"],
        dst=[],
        diff=['DROP TYPE "public"."r_int"'],
    )


async def test_range_type_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical range type on both sides -> no migration SQL.
    """
    await gen_setup.assert_diff(
        both=["CREATE TYPE r_int AS RANGE (subtype = integer)"],
        src=[],
        dst=[],
        diff=[],
    )


async def test_range_type_subtype_change_recreates(gen_setup: GenerateSetup) -> None:
    """
    A range type has no ALTER form, so changing its subtype is a drop + recreate. Both
    statements land in the create phase (drop first) so the recreate converges.
    """
    await gen_setup.assert_diff(
        src=["CREATE TYPE r AS RANGE (subtype = integer)"],
        dst=["CREATE TYPE r AS RANGE (subtype = bigint)"],
        diff=[
            'DROP TYPE "public"."r"',
            'CREATE TYPE "public"."r" AS RANGE (SUBTYPE = bigint)',
        ],
    )


async def test_range_type_subtype_diff_change_recreates(gen_setup: GenerateSetup) -> None:
    """
    Adding a SUBTYPE_DIFF to an existing range (same subtype) is still a drop + recreate:
    the property set differs and there is no ALTER form.
    """
    await gen_setup.assert_diff(
        src=["CREATE TYPE r_float AS RANGE (subtype = float8)"],
        dst=["CREATE TYPE r_float AS RANGE (subtype = float8, subtype_diff = float8mi)"],
        diff=[
            'DROP TYPE "public"."r_float"',
            'CREATE TYPE "public"."r_float" AS RANGE (SUBTYPE = double precision, SUBTYPE_DIFF = float8mi)',
        ],
    )


async def test_range_type_comment(gen_setup: GenerateSetup) -> None:
    """
    A range type comment is synced with COMMENT ON TYPE.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE TYPE r_int AS RANGE (subtype = integer)",
            "COMMENT ON TYPE r_int IS 'hi'",
        ],
        diff=[
            'CREATE TYPE "public"."r_int" AS RANGE (SUBTYPE = integer)',
            'COMMENT ON TYPE "public"."r_int" IS \'hi\'',
        ],
    )


async def test_range_type_used_by_table_column(gen_setup: GenerateSetup) -> None:
    """
    A range type and a table column that uses it are created together: the type's CREATE is
    phased before the table, so the column's type exists when the table is created.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE TYPE r_int AS RANGE (subtype = integer)",
            "CREATE TABLE t (span r_int)",
        ],
        diff=[
            'CREATE TYPE "public"."r_int" AS RANGE (SUBTYPE = integer)',
            'CREATE TABLE "public"."t" ("span" public.r_int)',
        ],
    )
