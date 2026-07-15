from tests._api.generate_setup import GenerateSetup


async def test_composite_type_create(gen_setup: GenerateSetup) -> None:
    """
    Composite type present in target but missing in source -> CREATE TYPE.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE TYPE pair AS (a integer, b integer)"],
        diff=['CREATE TYPE "public"."pair" AS ("a" integer, "b" integer)'],
    )


async def test_composite_type_create_empty(gen_setup: GenerateSetup) -> None:
    """
    A field-less composite type (CREATE TYPE ... AS ()) present only in target must still
    be seen and created -- the introspection join must not drop the zero-field type, or
    the diff silently claims convergence while the type is missing.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=["CREATE TYPE empty AS ()"],
        diff=['CREATE TYPE "public"."empty" AS ()'],
    )


async def test_composite_type_drop(gen_setup: GenerateSetup) -> None:
    """
    Composite type present in source but missing in target -> DROP TYPE.
    """
    await gen_setup.assert_diff(
        src=["CREATE TYPE pair AS (a integer, b integer)"],
        dst=[],
        diff=['DROP TYPE "public"."pair"'],
    )


async def test_composite_type_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical composite type on both sides -> no migration SQL.
    """
    await gen_setup.assert_diff(
        both=["CREATE TYPE pair AS (a integer, b integer)"],
        src=[],
        dst=[],
        diff=[],
    )


async def test_composite_type_field_change_raises(gen_setup: GenerateSetup) -> None:
    """
    A field-level change on a type present in both sides is not supported yet (ALTER TYPE
    deferred) -> UnsupportedChangeError.
    """
    await gen_setup.assert_unsupported(
        src=["CREATE TYPE pair AS (a integer, b integer)"],
        dst=["CREATE TYPE pair AS (a integer, b bigint)"],
        match="Composite type field change is not supported",
    )


async def test_composite_type_comment(gen_setup: GenerateSetup) -> None:
    """
    A composite type comment is synced with COMMENT ON TYPE.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE TYPE pair AS (a integer, b integer)",
            "COMMENT ON TYPE pair IS 'hi'",
        ],
        diff=[
            'CREATE TYPE "public"."pair" AS ("a" integer, "b" integer)',
            'COMMENT ON TYPE "public"."pair" IS \'hi\'',
        ],
    )
