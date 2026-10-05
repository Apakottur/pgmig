from tests._api.generate_setup import GenerateSetup


async def test_safe_not_null_set_not_null(gen_setup: GenerateSetup) -> None:
    """
    With safe_not_null, SET NOT NULL is preceded by a validated CHECK (col IS NOT NULL)
    that lets Postgres skip the full-table scan, and the CHECK is dropped afterwards.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (name text)"],
        dst=["CREATE TABLE person (name text NOT NULL)"],
        diff=[
            'ALTER TABLE "public"."person" ADD CONSTRAINT "pgmig_name_not_null" CHECK ("name" IS NOT NULL) NOT VALID',
            'ALTER TABLE "public"."person" VALIDATE CONSTRAINT "pgmig_name_not_null"',
            'ALTER TABLE "public"."person" ALTER COLUMN "name" SET NOT NULL',
            'ALTER TABLE "public"."person" DROP CONSTRAINT "pgmig_name_not_null"',
        ],
        safe_not_null=True,
    )


async def test_safe_not_null_with_existing_rows(gen_setup: GenerateSetup) -> None:
    """
    With safe_not_null, existing non-null rows validate and the column becomes NOT NULL.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (name text)", "INSERT INTO person VALUES ('a'), ('b')"],
        dst=["CREATE TABLE person (name text NOT NULL)"],
        diff=[
            'ALTER TABLE "public"."person" ADD CONSTRAINT "pgmig_name_not_null" CHECK ("name" IS NOT NULL) NOT VALID',
            'ALTER TABLE "public"."person" VALIDATE CONSTRAINT "pgmig_name_not_null"',
            'ALTER TABLE "public"."person" ALTER COLUMN "name" SET NOT NULL',
            'ALTER TABLE "public"."person" DROP CONSTRAINT "pgmig_name_not_null"',
        ],
        safe_not_null=True,
    )


async def test_safe_not_null_drop_not_null_unchanged(gen_setup: GenerateSetup) -> None:
    """
    DROP NOT NULL takes no scan, so safe_not_null leaves it unchanged.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (name text NOT NULL)"],
        dst=["CREATE TABLE person (name text)"],
        diff=['ALTER TABLE "public"."person" ALTER COLUMN "name" DROP NOT NULL'],
        safe_not_null=True,
    )


async def test_safe_not_null_add_identity(gen_setup: GenerateSetup) -> None:
    """
    A nullable column gaining an identity needs SET NOT NULL before the ADD; with
    safe_not_null that SET NOT NULL goes through the validated CHECK too.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (id integer)"],
        dst=["CREATE TABLE person (id integer GENERATED ALWAYS AS IDENTITY)"],
        diff=[
            'ALTER TABLE "public"."person" ADD CONSTRAINT "pgmig_id_not_null" CHECK ("id" IS NOT NULL) NOT VALID',
            'ALTER TABLE "public"."person" VALIDATE CONSTRAINT "pgmig_id_not_null"',
            'ALTER TABLE "public"."person" ALTER COLUMN "id" SET NOT NULL',
            'ALTER TABLE "public"."person" DROP CONSTRAINT "pgmig_id_not_null"',
            'ALTER TABLE "public"."person" ALTER COLUMN "id" ADD GENERATED ALWAYS AS IDENTITY',
        ],
        safe_not_null=True,
    )


async def test_safe_not_null_partitioned_table(gen_setup: GenerateSetup) -> None:
    """
    On a partitioned table the CHECK and the SET NOT NULL both recurse to the partitions.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE event (id integer, name text) PARTITION BY RANGE (id)",
            "CREATE TABLE event_p1 PARTITION OF event FOR VALUES FROM (0) TO (100)",
        ],
        dst=[
            "CREATE TABLE event (id integer, name text NOT NULL) PARTITION BY RANGE (id)",
            "CREATE TABLE event_p1 PARTITION OF event FOR VALUES FROM (0) TO (100)",
        ],
        diff=[
            'ALTER TABLE "public"."event" ADD CONSTRAINT "pgmig_name_not_null" CHECK ("name" IS NOT NULL) NOT VALID',
            'ALTER TABLE "public"."event" VALIDATE CONSTRAINT "pgmig_name_not_null"',
            'ALTER TABLE "public"."event" ALTER COLUMN "name" SET NOT NULL',
            'ALTER TABLE "public"."event" DROP CONSTRAINT "pgmig_name_not_null"',
        ],
        safe_not_null=True,
    )
