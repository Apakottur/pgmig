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


async def test_composite_type_add_attribute(gen_setup: GenerateSetup) -> None:
    """
    An attribute present in target only is added in place with ALTER TYPE ... ADD ATTRIBUTE.
    """
    await gen_setup.assert_diff(
        src=["CREATE TYPE pair AS (a integer)"],
        dst=["CREATE TYPE pair AS (a integer, b integer)"],
        diff=['ALTER TYPE "public"."pair" ADD ATTRIBUTE "b" integer CASCADE'],
    )


async def test_composite_type_drop_attribute(gen_setup: GenerateSetup) -> None:
    """
    An attribute present in source only is removed in place with ALTER TYPE ... DROP ATTRIBUTE.
    """
    await gen_setup.assert_diff(
        src=["CREATE TYPE pair AS (a integer, b integer)"],
        dst=["CREATE TYPE pair AS (a integer)"],
        diff=['ALTER TYPE "public"."pair" DROP ATTRIBUTE "b" CASCADE'],
    )


async def test_composite_type_alter_attribute_type(gen_setup: GenerateSetup) -> None:
    """
    An attribute whose type differs is changed in place with ALTER TYPE ... ALTER ATTRIBUTE ... TYPE.
    """
    await gen_setup.assert_diff(
        src=["CREATE TYPE pair AS (a integer, b integer)"],
        dst=["CREATE TYPE pair AS (a integer, b bigint)"],
        diff=['ALTER TYPE "public"."pair" ALTER ATTRIBUTE "b" TYPE bigint CASCADE'],
    )


async def test_composite_type_combined_attribute_changes(
    gen_setup: GenerateSetup,
) -> None:
    """
    A type with a dropped, a retyped, and an added attribute emits one statement each:
    drops first, then type changes, then additions.
    """
    await gen_setup.assert_diff(
        src=["CREATE TYPE rec AS (a integer, b integer, c integer)"],
        dst=["CREATE TYPE rec AS (a bigint, c integer, d integer)"],
        diff=[
            'ALTER TYPE "public"."rec" DROP ATTRIBUTE "b" CASCADE',
            'ALTER TYPE "public"."rec" ALTER ATTRIBUTE "a" TYPE bigint CASCADE',
            'ALTER TYPE "public"."rec" ADD ATTRIBUTE "d" integer CASCADE',
        ],
    )


async def test_composite_type_add_attribute_of_new_type(
    gen_setup: GenerateSetup,
) -> None:
    """
    An added attribute whose type is another composite type created in the same migration must
    be emitted after that type's CREATE, even though the alter and the create share the
    TYPE_CREATE phase.
    """
    await gen_setup.assert_diff(
        src=["CREATE TYPE pair AS (a integer)"],
        dst=[
            "CREATE TYPE z_new AS (v integer)",
            "CREATE TYPE pair AS (a integer, b z_new)",
        ],
        diff=[
            'CREATE TYPE "public"."z_new" AS ("v" integer)',
            'ALTER TYPE "public"."pair" ADD ATTRIBUTE "b" public.z_new CASCADE',
        ],
    )


async def test_composite_type_attribute_change_on_type_used_by_table(
    gen_setup: GenerateSetup,
) -> None:
    """
    Altering a composite type whose value is used by a table column requires CASCADE so the
    change propagates to the table's row type; the migration must converge.
    """
    await gen_setup.assert_diff(
        both=["CREATE TYPE pair AS (a integer)"],
        src=["CREATE TABLE t (p pair)"],
        dst=["ALTER TYPE pair ADD ATTRIBUTE b integer", "CREATE TABLE t (p pair)"],
        diff=['ALTER TYPE "public"."pair" ADD ATTRIBUTE "b" integer CASCADE'],
    )


async def test_composite_type_attribute_reorder_raises(
    gen_setup: GenerateSetup,
) -> None:
    """
    Reordering existing attributes has no in-place ALTER form (ADD only appends), so it stays
    unsupported.
    """
    await gen_setup.assert_unsupported(
        src=["CREATE TYPE pair AS (a integer, b integer)"],
        dst=["CREATE TYPE pair AS (b integer, a integer)"],
        match="Composite type attribute reorder is not supported",
    )


async def test_composite_type_create_ordered_by_dependency(
    gen_setup: GenerateSetup,
) -> None:
    """
    A composite type whose field is another composite type must be created after the type it
    references, regardless of name order. Here the outer type (`a_point`) sorts before the
    inner one (`z_coord`) alphabetically, so a name-ordered create emits `a_point` first and
    Postgres rejects it (missing type). The dependency sort must emit `z_coord` first.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE TYPE z_coord AS (v integer)",
            "CREATE TYPE a_point AS (c z_coord)",
        ],
        diff=[
            'CREATE TYPE "public"."z_coord" AS ("v" integer)',
            'CREATE TYPE "public"."a_point" AS ("c" public.z_coord)',
        ],
    )


async def test_composite_type_array_field_ordered_by_dependency(
    gen_setup: GenerateSetup,
) -> None:
    """
    A field that is an *array* of another composite type creates the same dependency: the
    element type must exist first. The outer type (`a_poly`) sorts before the inner one
    (`z_coord`), so only the dependency sort (resolving the array element) emits `z_coord`
    first.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE TYPE z_coord AS (v integer)",
            "CREATE TYPE a_poly AS (pts z_coord[])",
        ],
        diff=[
            'CREATE TYPE "public"."z_coord" AS ("v" integer)',
            'CREATE TYPE "public"."a_poly" AS ("pts" public.z_coord[])',
        ],
    )


async def test_composite_type_drop_ordered_by_dependency(
    gen_setup: GenerateSetup,
) -> None:
    """
    Dropping composite types must go dependent-first. Here the outer type (`z_outer`) sorts
    after the inner one (`a_inner`) alphabetically, so a name-ordered drop emits `a_inner`
    first and Postgres rejects it (still used by `z_outer`). The dependency sort must drop
    `z_outer` first.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE TYPE a_inner AS (v integer)",
            "CREATE TYPE z_outer AS (c a_inner)",
        ],
        dst=[],
        diff=[
            'DROP TYPE "public"."z_outer"',
            'DROP TYPE "public"."a_inner"',
        ],
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
