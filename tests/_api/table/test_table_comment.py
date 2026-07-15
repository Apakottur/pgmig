from tests._api.generate_setup import GenerateSetup


async def test_table_create_with_comment(gen_setup: GenerateSetup) -> None:
    """
    Table created on target with a comment -> CREATE TABLE then COMMENT ON TABLE.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE TABLE person (name text)",
            "COMMENT ON TABLE person IS 'people'",
        ],
        diff=[
            'CREATE TABLE "public"."person" ("name" text)',
            'COMMENT ON TABLE "public"."person" IS \'people\'',
        ],
    )


async def test_table_comment_added(gen_setup: GenerateSetup) -> None:
    """
    Identical table both sides, comment only on target -> COMMENT ON TABLE.
    """
    await gen_setup.assert_diff(
        both=["CREATE TABLE person (name text)"],
        src=[],
        dst=["COMMENT ON TABLE person IS 'people'"],
        diff=['COMMENT ON TABLE "public"."person" IS \'people\''],
    )


async def test_table_comment_changed(gen_setup: GenerateSetup) -> None:
    """
    Same table both sides with differing comments -> COMMENT ON TABLE with target's.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (name text)",
            "COMMENT ON TABLE person IS 'old'",
        ],
        dst=[
            "CREATE TABLE person (name text)",
            "COMMENT ON TABLE person IS 'new'",
        ],
        diff=['COMMENT ON TABLE "public"."person" IS \'new\''],
    )


async def test_table_comment_removed(gen_setup: GenerateSetup) -> None:
    """
    Comment on source but none on target -> COMMENT ON TABLE ... IS NULL.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (name text)",
            "COMMENT ON TABLE person IS 'people'",
        ],
        dst=["CREATE TABLE person (name text)"],
        diff=['COMMENT ON TABLE "public"."person" IS NULL'],
    )


async def test_table_comment_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Same table and same comment on both sides -> no migration SQL.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (name text)",
            "COMMENT ON TABLE person IS 'people'",
        ],
        dst=[
            "CREATE TABLE person (name text)",
            "COMMENT ON TABLE person IS 'people'",
        ],
        diff=[],
    )


async def test_table_comment_with_single_quote(gen_setup: GenerateSetup) -> None:
    """
    Comment containing a single quote is escaped by doubling.
    """
    await gen_setup.assert_diff(
        both=["CREATE TABLE person (name text)"],
        src=[],
        dst=["COMMENT ON TABLE person IS 'it''s people'"],
        diff=["COMMENT ON TABLE \"public\".\"person\" IS 'it''s people'"],
    )
