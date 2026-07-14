import pytest

from tests.api.generate_setup import GenerateSetup


def test_enum_create(gen_setup: GenerateSetup) -> None:
    """
    Enum present in target but missing in source -> CREATE TYPE ... AS ENUM.
    """
    gen_setup.dst.execute("CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy')")

    gen_setup.assert_migration_sql("CREATE TYPE \"public\".\"mood\" AS ENUM ('sad', 'ok', 'happy');")


def test_enum_drop(gen_setup: GenerateSetup) -> None:
    """
    Enum present in source but missing in target -> DROP TYPE.
    """
    gen_setup.src.execute("CREATE TYPE mood AS ENUM ('sad', 'happy')")

    gen_setup.assert_migration_sql('DROP TYPE "public"."mood";')


def test_enum_add_value_appended(gen_setup: GenerateSetup) -> None:
    """
    A value appended at the end -> ALTER TYPE ADD VALUE.
    """
    gen_setup.src.execute("CREATE TYPE mood AS ENUM ('sad', 'ok')")
    gen_setup.dst.execute("CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy')")

    gen_setup.assert_migration_sql('ALTER TYPE "public"."mood" ADD VALUE \'happy\';')


def test_enum_add_value_inserted(gen_setup: GenerateSetup) -> None:
    """
    A value inserted in the middle -> ALTER TYPE ADD VALUE ... BEFORE.
    """
    gen_setup.src.execute("CREATE TYPE mood AS ENUM ('sad', 'happy')")
    gen_setup.dst.execute("CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy')")

    gen_setup.assert_migration_sql("ALTER TYPE \"public\".\"mood\" ADD VALUE 'ok' BEFORE 'happy';")


def test_enum_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical enum on both sides -> no migration SQL.
    """
    gen_setup.src.execute("CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy')")
    gen_setup.dst.execute("CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy')")

    gen_setup.assert_migration_sql("")


def test_enum_value_removal_unsupported(gen_setup: GenerateSetup) -> None:
    """
    Removing a value is unsupported -> NotImplementedError.
    """
    gen_setup.src.execute("CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy')")
    gen_setup.dst.execute("CREATE TYPE mood AS ENUM ('sad', 'happy')")

    with pytest.raises(NotImplementedError):
        gen_setup.assert_migration_sql("")


def test_enum_value_reorder_unsupported(gen_setup: GenerateSetup) -> None:
    """
    Reordering values is unsupported -> NotImplementedError.
    """
    gen_setup.src.execute("CREATE TYPE mood AS ENUM ('sad', 'happy')")
    gen_setup.dst.execute("CREATE TYPE mood AS ENUM ('happy', 'sad')")

    with pytest.raises(NotImplementedError):
        gen_setup.assert_migration_sql("")


def test_enum_typed_column_ordered_after_type(gen_setup: GenerateSetup) -> None:
    """
    A new enum and a new table with a column of that type: CREATE TYPE precedes CREATE TABLE.
    """
    gen_setup.dst.execute("CREATE TYPE mood AS ENUM ('sad', 'happy')")
    gen_setup.dst.execute("CREATE TABLE person (feeling mood)")

    gen_setup.assert_migration_sql(
        [
            "CREATE TYPE \"public\".\"mood\" AS ENUM ('sad', 'happy');",
            'CREATE TABLE "public"."person" ("feeling" public.mood);',
        ]
    )


def test_enum_create_with_comment(gen_setup: GenerateSetup) -> None:
    """
    Enum created on target with a comment -> CREATE TYPE then COMMENT ON TYPE.
    """
    gen_setup.dst.execute("CREATE TYPE mood AS ENUM ('sad', 'happy')")
    gen_setup.dst.execute("COMMENT ON TYPE mood IS 'feelings'")

    gen_setup.assert_migration_sql(
        [
            "CREATE TYPE \"public\".\"mood\" AS ENUM ('sad', 'happy');",
            'COMMENT ON TYPE "public"."mood" IS \'feelings\';',
        ]
    )


def test_enum_comment_added(gen_setup: GenerateSetup) -> None:
    """
    Identical enum both sides, comment only on target -> COMMENT ON TYPE.
    """
    gen_setup.execute_both("CREATE TYPE mood AS ENUM ('sad', 'happy')")
    gen_setup.dst.execute("COMMENT ON TYPE mood IS 'feelings'")

    gen_setup.assert_migration_sql('COMMENT ON TYPE "public"."mood" IS \'feelings\';')


def test_enum_comment_changed(gen_setup: GenerateSetup) -> None:
    """
    Same enum both sides with differing comments -> COMMENT ON TYPE with target's.
    """
    gen_setup.execute_both("CREATE TYPE mood AS ENUM ('sad', 'happy')")
    gen_setup.src.execute("COMMENT ON TYPE mood IS 'old'")
    gen_setup.dst.execute("COMMENT ON TYPE mood IS 'new'")

    gen_setup.assert_migration_sql('COMMENT ON TYPE "public"."mood" IS \'new\';')


def test_enum_comment_removed(gen_setup: GenerateSetup) -> None:
    """
    Comment on source enum but none on target -> COMMENT ON TYPE ... IS NULL.
    """
    gen_setup.execute_both("CREATE TYPE mood AS ENUM ('sad', 'happy')")
    gen_setup.src.execute("COMMENT ON TYPE mood IS 'feelings'")

    gen_setup.assert_migration_sql('COMMENT ON TYPE "public"."mood" IS NULL;')


def test_enum_comment_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Same enum and same comment on both sides -> no migration SQL.
    """
    gen_setup.execute_both("CREATE TYPE mood AS ENUM ('sad', 'happy')")
    gen_setup.execute_both("COMMENT ON TYPE mood IS 'feelings'")

    gen_setup.assert_migration_sql("")
