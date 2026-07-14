from tests.api.generate_setup import GenerateSetup


def test_enum_create(gen_setup: GenerateSetup) -> None:
    """
    Enum present in target but missing in source -> CREATE TYPE ... AS ENUM.
    """
    gen_setup.assert_diff(
        src=[],
        dst=["CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy')"],
        diff=["CREATE TYPE \"public\".\"mood\" AS ENUM ('sad', 'ok', 'happy')"],
    )


def test_enum_create_empty(gen_setup: GenerateSetup) -> None:
    """
    A member-less enum (CREATE TYPE ... AS ENUM ()) present only in target must still be
    seen and created -- the introspection join must not drop the zero-member type, or the
    diff silently claims convergence while the type is missing.
    """
    gen_setup.assert_diff(
        src=[],
        dst=["CREATE TYPE mood AS ENUM ()"],
        diff=['CREATE TYPE "public"."mood" AS ENUM ()'],
    )


def test_enum_drop(gen_setup: GenerateSetup) -> None:
    """
    Enum present in source but missing in target -> DROP TYPE.
    """
    gen_setup.assert_diff(
        src=["CREATE TYPE mood AS ENUM ('sad', 'happy')"],
        dst=[],
        diff=['DROP TYPE "public"."mood"'],
    )


def test_enum_add_value_appended(gen_setup: GenerateSetup) -> None:
    """
    A value appended at the end -> ALTER TYPE ADD VALUE.
    """
    gen_setup.assert_diff(
        src=["CREATE TYPE mood AS ENUM ('sad', 'ok')"],
        dst=["CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy')"],
        diff=['ALTER TYPE "public"."mood" ADD VALUE \'happy\''],
    )


def test_enum_add_value_inserted(gen_setup: GenerateSetup) -> None:
    """
    A value inserted in the middle -> ALTER TYPE ADD VALUE ... BEFORE.
    """
    gen_setup.assert_diff(
        src=["CREATE TYPE mood AS ENUM ('sad', 'happy')"],
        dst=["CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy')"],
        diff=["ALTER TYPE \"public\".\"mood\" ADD VALUE 'ok' BEFORE 'happy'"],
    )


def test_enum_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical enum on both sides -> no migration SQL.
    """
    gen_setup.assert_diff(
        src=["CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy')"],
        dst=["CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy')"],
        diff=[],
    )


def test_enum_value_removal_unsupported(gen_setup: GenerateSetup) -> None:
    """
    Removing a value is unsupported -> UnsupportedChangeError.
    """
    gen_setup.assert_unsupported(
        src=["CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy')"],
        dst=["CREATE TYPE mood AS ENUM ('sad', 'happy')"],
    )


def test_enum_value_reorder_unsupported(gen_setup: GenerateSetup) -> None:
    """
    Reordering values is unsupported -> UnsupportedChangeError.
    """
    gen_setup.assert_unsupported(
        src=["CREATE TYPE mood AS ENUM ('sad', 'happy')"],
        dst=["CREATE TYPE mood AS ENUM ('happy', 'sad')"],
    )


def test_enum_typed_column_ordered_after_type(gen_setup: GenerateSetup) -> None:
    """
    A new enum and a new table with a column of that type: CREATE TYPE precedes CREATE TABLE.
    """
    gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE TYPE mood AS ENUM ('sad', 'happy')",
            "CREATE TABLE person (feeling mood)",
        ],
        diff=[
            "CREATE TYPE \"public\".\"mood\" AS ENUM ('sad', 'happy')",
            'CREATE TABLE "public"."person" ("feeling" public.mood)',
        ],
    )


def test_enum_create_with_comment(gen_setup: GenerateSetup) -> None:
    """
    Enum created on target with a comment -> CREATE TYPE then COMMENT ON TYPE.
    """
    gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE TYPE mood AS ENUM ('sad', 'happy')",
            "COMMENT ON TYPE mood IS 'feelings'",
        ],
        diff=[
            "CREATE TYPE \"public\".\"mood\" AS ENUM ('sad', 'happy')",
            'COMMENT ON TYPE "public"."mood" IS \'feelings\'',
        ],
    )


def test_enum_comment_added(gen_setup: GenerateSetup) -> None:
    """
    Identical enum both sides, comment only on target -> COMMENT ON TYPE.
    """
    gen_setup.assert_diff(
        both=["CREATE TYPE mood AS ENUM ('sad', 'happy')"],
        src=[],
        dst=["COMMENT ON TYPE mood IS 'feelings'"],
        diff=['COMMENT ON TYPE "public"."mood" IS \'feelings\''],
    )


def test_enum_comment_changed(gen_setup: GenerateSetup) -> None:
    """
    Same enum both sides with differing comments -> COMMENT ON TYPE with target's.
    """
    gen_setup.assert_diff(
        both=["CREATE TYPE mood AS ENUM ('sad', 'happy')"],
        src=["COMMENT ON TYPE mood IS 'old'"],
        dst=["COMMENT ON TYPE mood IS 'new'"],
        diff=['COMMENT ON TYPE "public"."mood" IS \'new\''],
    )


def test_enum_comment_removed(gen_setup: GenerateSetup) -> None:
    """
    Comment on source enum but none on target -> COMMENT ON TYPE ... IS NULL.
    """
    gen_setup.assert_diff(
        both=["CREATE TYPE mood AS ENUM ('sad', 'happy')"],
        src=["COMMENT ON TYPE mood IS 'feelings'"],
        dst=[],
        diff=['COMMENT ON TYPE "public"."mood" IS NULL'],
    )


def test_enum_comment_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Same enum and same comment on both sides -> no migration SQL.
    """
    gen_setup.assert_diff(
        both=[
            "CREATE TYPE mood AS ENUM ('sad', 'happy')",
            "COMMENT ON TYPE mood IS 'feelings'",
        ],
        src=[],
        dst=[],
        diff=[],
    )
