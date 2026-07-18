from tests._api.generate_setup import GenerateSetup


async def test_enum_rename_and_insert_rewrite(gen_setup: GenerateSetup) -> None:
    """
    A rename combined with an insertion is not a pure positional rename nor a clean append, so
    it falls back to a full type rewrite (the general path for any other value change).
    """
    await gen_setup.assert_diff(
        src=["CREATE TYPE mood AS ENUM ('sad', 'ok')"],
        dst=["CREATE TYPE mood AS ENUM ('sad', 'fine', 'happy')"],
        diff=[
            'ALTER TYPE "public"."mood" RENAME TO "mood__pgmig_tmp"',
            "CREATE TYPE \"public\".\"mood\" AS ENUM ('sad', 'fine', 'happy')",
            'DROP TYPE "public"."mood__pgmig_tmp"',
        ],
    )


async def test_enum_value_removal_rewrite(gen_setup: GenerateSetup) -> None:
    """
    Removing a value has no ALTER form -> type rewrite (rename old aside, create new, drop old).
    With no dependent columns there is no ALTER TABLE step.
    """
    await gen_setup.assert_diff(
        src=["CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy')"],
        dst=["CREATE TYPE mood AS ENUM ('sad', 'happy')"],
        diff=[
            'ALTER TYPE "public"."mood" RENAME TO "mood__pgmig_tmp"',
            "CREATE TYPE \"public\".\"mood\" AS ENUM ('sad', 'happy')",
            'DROP TYPE "public"."mood__pgmig_tmp"',
        ],
    )


async def test_enum_value_reorder_rewrite(gen_setup: GenerateSetup) -> None:
    """
    Reordering values has no ALTER form -> type rewrite.
    """
    await gen_setup.assert_diff(
        src=["CREATE TYPE mood AS ENUM ('sad', 'happy')"],
        dst=["CREATE TYPE mood AS ENUM ('happy', 'sad')"],
        diff=[
            'ALTER TYPE "public"."mood" RENAME TO "mood__pgmig_tmp"',
            "CREATE TYPE \"public\".\"mood\" AS ENUM ('happy', 'sad')",
            'DROP TYPE "public"."mood__pgmig_tmp"',
        ],
    )


async def test_enum_rewrite_retypes_dependent_column(gen_setup: GenerateSetup) -> None:
    """
    A removal with a dependent column retypes the column through text between the recreate and
    the drop of the old type.
    """
    await gen_setup.assert_diff(
        src=["CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy')", "CREATE TABLE t (c mood)"],
        dst=["CREATE TYPE mood AS ENUM ('sad', 'happy')", "CREATE TABLE t (c mood)"],
        diff=[
            'ALTER TYPE "public"."mood" RENAME TO "mood__pgmig_tmp"',
            "CREATE TYPE \"public\".\"mood\" AS ENUM ('sad', 'happy')",
            'ALTER TABLE "public"."t" ALTER COLUMN "c" TYPE public.mood USING "c"::text::public.mood',
            'DROP TYPE "public"."mood__pgmig_tmp"',
        ],
    )


async def test_enum_rewrite_column_default_dropped_and_restored(gen_setup: GenerateSetup) -> None:
    """
    A dependent column's default references the enum: drop it before the type change, re-add
    it after.
    """
    await gen_setup.assert_diff(
        src=["CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy')", "CREATE TABLE t (c mood DEFAULT 'sad')"],
        dst=["CREATE TYPE mood AS ENUM ('sad', 'happy')", "CREATE TABLE t (c mood DEFAULT 'sad')"],
        diff=[
            'ALTER TYPE "public"."mood" RENAME TO "mood__pgmig_tmp"',
            "CREATE TYPE \"public\".\"mood\" AS ENUM ('sad', 'happy')",
            'ALTER TABLE "public"."t" ALTER COLUMN "c" DROP DEFAULT',
            'ALTER TABLE "public"."t" ALTER COLUMN "c" TYPE public.mood USING "c"::text::public.mood',
            'ALTER TABLE "public"."t" ALTER COLUMN "c" SET DEFAULT \'sad\'::public.mood',
            'DROP TYPE "public"."mood__pgmig_tmp"',
        ],
    )


async def test_enum_rewrite_array_column(gen_setup: GenerateSetup) -> None:
    """
    An enum-array column (mood[]) retypes through text[] and back to the array type.
    """
    await gen_setup.assert_diff(
        src=["CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy')", "CREATE TABLE t (c mood[])"],
        dst=["CREATE TYPE mood AS ENUM ('sad', 'happy')", "CREATE TABLE t (c mood[])"],
        diff=[
            'ALTER TYPE "public"."mood" RENAME TO "mood__pgmig_tmp"',
            "CREATE TYPE \"public\".\"mood\" AS ENUM ('sad', 'happy')",
            'ALTER TABLE "public"."t" ALTER COLUMN "c" TYPE public.mood[] USING "c"::text[]::public.mood[]',
            'DROP TYPE "public"."mood__pgmig_tmp"',
        ],
    )


async def test_enum_rewrite_multiple_dependent_columns(gen_setup: GenerateSetup) -> None:
    """
    Every dependent column across tables is retyped, with a single drop of the old type.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy')",
            "CREATE TABLE t1 (c mood)",
            "CREATE TABLE t2 (c mood)",
        ],
        dst=[
            "CREATE TYPE mood AS ENUM ('sad', 'happy')",
            "CREATE TABLE t1 (c mood)",
            "CREATE TABLE t2 (c mood)",
        ],
        diff=[
            'ALTER TYPE "public"."mood" RENAME TO "mood__pgmig_tmp"',
            "CREATE TYPE \"public\".\"mood\" AS ENUM ('sad', 'happy')",
            'ALTER TABLE "public"."t1" ALTER COLUMN "c" TYPE public.mood USING "c"::text::public.mood',
            'ALTER TABLE "public"."t2" ALTER COLUMN "c" TYPE public.mood USING "c"::text::public.mood',
            'DROP TYPE "public"."mood__pgmig_tmp"',
        ],
    )


async def test_enum_rewrite_reapplies_comment(gen_setup: GenerateSetup) -> None:
    """
    The recreate drops the type comment; an unchanged comment is re-applied so it does not
    silently disappear.
    """
    await gen_setup.assert_diff(
        src=["CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy')", "COMMENT ON TYPE mood IS 'feelings'"],
        dst=["CREATE TYPE mood AS ENUM ('sad', 'happy')", "COMMENT ON TYPE mood IS 'feelings'"],
        diff=[
            'ALTER TYPE "public"."mood" RENAME TO "mood__pgmig_tmp"',
            "CREATE TYPE \"public\".\"mood\" AS ENUM ('sad', 'happy')",
            'COMMENT ON TYPE "public"."mood" IS \'feelings\'',
            'DROP TYPE "public"."mood__pgmig_tmp"',
        ],
    )


async def test_enum_rewrite_generated_column_unsupported(gen_setup: GenerateSetup) -> None:
    """
    A generated column of the enum type cannot be retyped (ALTER COLUMN TYPE rejects USING on
    a generated column) -> unsupported.
    """
    await gen_setup.assert_unsupported(
        src=[
            "CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy')",
            "CREATE TABLE t (c mood, d mood GENERATED ALWAYS AS (c) STORED)",
        ],
        dst=[
            "CREATE TYPE mood AS ENUM ('sad', 'happy')",
            "CREATE TABLE t (c mood, d mood GENERATED ALWAYS AS (c) STORED)",
        ],
        match=r"generated column",
    )


async def test_enum_rewrite_indexed_column_unsupported(gen_setup: GenerateSetup) -> None:
    """
    A dependent column used by an index is out of scope for the rewrite -> unsupported.
    """
    await gen_setup.assert_unsupported(
        src=[
            "CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy')",
            "CREATE TABLE t (c mood)",
            "CREATE INDEX t_c_idx ON t (c)",
        ],
        dst=[
            "CREATE TYPE mood AS ENUM ('sad', 'happy')",
            "CREATE TABLE t (c mood)",
            "CREATE INDEX t_c_idx ON t (c)",
        ],
        match=r"used by an index",
    )


async def test_enum_rewrite_constrained_column_unsupported(gen_setup: GenerateSetup) -> None:
    """
    A dependent column used by a constraint is out of scope for the rewrite -> unsupported.
    """
    await gen_setup.assert_unsupported(
        src=[
            "CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy')",
            "CREATE TABLE t (c mood, CONSTRAINT t_c_not_x CHECK (c <> 'happy'))",
        ],
        dst=[
            "CREATE TYPE mood AS ENUM ('sad', 'happy')",
            "CREATE TABLE t (c mood, CONSTRAINT t_c_not_x CHECK (c <> 'happy'))",
        ],
        match=r"used by a constraint",
    )


async def test_enum_rewrite_domain_over_enum_unsupported(gen_setup: GenerateSetup) -> None:
    """
    A domain defined over the enum would break on the recreate and its columns are invisible to
    the column-dependency join -> unsupported.
    """
    await gen_setup.assert_unsupported(
        src=["CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy')", "CREATE DOMAIN feeling AS mood"],
        dst=["CREATE TYPE mood AS ENUM ('sad', 'happy')", "CREATE DOMAIN feeling AS mood"],
        match=r"domain .* is defined over the enum",
    )


async def test_enum_rewrite_view_read_column_unsupported(gen_setup: GenerateSetup) -> None:
    """
    A view reading a dependent column blocks ALTER COLUMN TYPE and is not caught by the
    retyped-reader recreate (the column's type name is unchanged) -> unsupported.
    """
    await gen_setup.assert_unsupported(
        src=[
            "CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy')",
            "CREATE TABLE t (c mood)",
            "CREATE VIEW v AS SELECT c FROM t",
        ],
        dst=[
            "CREATE TYPE mood AS ENUM ('sad', 'happy')",
            "CREATE TABLE t (c mood)",
            "CREATE VIEW v AS SELECT c FROM t",
        ],
        match=r"read by a view or materialized view",
    )
