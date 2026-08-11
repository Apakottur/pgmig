from tests._api.generate_setup import GenerateSetup


async def test_table_column_create_with_comment(gen_setup: GenerateSetup) -> None:
    """
    A created table with a commented column -> CREATE TABLE then COMMENT ON COLUMN.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE TABLE person (name text)",
            "COMMENT ON COLUMN person.name IS 'full name'",
        ],
        diff=[
            'CREATE TABLE "public"."person" ("name" text)',
            'COMMENT ON COLUMN "public"."person"."name" IS \'full name\'',
        ],
    )


async def test_table_column_add_with_comment(gen_setup: GenerateSetup) -> None:
    """
    A column added to an existing table with a comment -> ADD COLUMN then COMMENT ON COLUMN.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (name text)"],
        dst=[
            "CREATE TABLE person (name text, age integer)",
            "COMMENT ON COLUMN person.age IS 'years'",
        ],
        diff=[
            'ALTER TABLE "public"."person" ADD COLUMN "age" integer',
            'COMMENT ON COLUMN "public"."person"."age" IS \'years\'',
        ],
    )


async def test_table_column_comment_added(gen_setup: GenerateSetup) -> None:
    """
    Identical column both sides, comment only on target -> COMMENT ON COLUMN.
    """
    await gen_setup.assert_diff(
        both=["CREATE TABLE person (name text)"],
        src=[],
        dst=["COMMENT ON COLUMN person.name IS 'full name'"],
        diff=['COMMENT ON COLUMN "public"."person"."name" IS \'full name\''],
    )


async def test_table_column_comment_removed(gen_setup: GenerateSetup) -> None:
    """
    Comment on source but none on target -> COMMENT ON COLUMN ... IS NULL.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (name text)",
            "COMMENT ON COLUMN person.name IS 'full name'",
        ],
        dst=["CREATE TABLE person (name text)"],
        diff=['COMMENT ON COLUMN "public"."person"."name" IS NULL'],
    )
