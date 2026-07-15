from tests._api.generate_setup import GenerateSetup


async def test_index_create(gen_setup: GenerateSetup) -> None:
    """
    Index present in target but missing in source -> CREATE INDEX.
    """
    await gen_setup.assert_diff(
        both=["CREATE TABLE person (name text)"],
        src=[],
        dst=["CREATE INDEX person_name_idx ON person (name)"],
        diff=["CREATE INDEX person_name_idx ON public.person USING btree (name)"],
    )


async def test_index_drop(gen_setup: GenerateSetup) -> None:
    """
    Index present in source but missing in target -> DROP INDEX.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (name text)",
            "CREATE INDEX person_name_idx ON person (name)",
        ],
        dst=["CREATE TABLE person (name text)"],
        diff=['DROP INDEX "public"."person_name_idx"'],
    )


async def test_index_rename(gen_setup: GenerateSetup) -> None:
    """
    Same definition on both sides, only the name differs -> ALTER INDEX RENAME.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (name text)",
            "CREATE INDEX person_name_old ON person (name)",
        ],
        dst=[
            "CREATE TABLE person (name text)",
            "CREATE INDEX person_name_new ON person (name)",
        ],
        diff=['ALTER INDEX "public"."person_name_old" RENAME TO "person_name_new"'],
    )


async def test_index_create_reusing_renamed_away_name_emits_comment(gen_setup: GenerateSetup) -> None:
    """
    Source has index `shared_idx`; target has `shared_idx` (redefined) plus `renamed_idx`
    whose definition matches source `shared_idx`. The differ renames shared_idx -> renamed_idx
    (same definition) and creates a fresh shared_idx. The fresh shared_idx was just created and
    carries no comment, so its target comment must be emitted -- even though resolving the new
    name back to the (renamed-away) source object would otherwise find a matching comment and
    suppress it, leaving a residual diff. A create reusing a vacated name is treated as
    recreated for comment purposes.
    """
    await gen_setup.assert_diff(
        both=["CREATE TABLE t (a int, b int)"],
        src=[
            "CREATE INDEX shared_idx ON t (a)",
            "COMMENT ON INDEX shared_idx IS 'kept'",
        ],
        dst=[
            "CREATE INDEX shared_idx ON t (b)",
            "COMMENT ON INDEX shared_idx IS 'kept'",
            "CREATE INDEX renamed_idx ON t (a)",
            "COMMENT ON INDEX renamed_idx IS 'kept'",
        ],
        diff=[
            'ALTER INDEX "public"."shared_idx" RENAME TO "renamed_idx"',
            "CREATE INDEX shared_idx ON public.t USING btree (b)",
            'COMMENT ON INDEX "public"."shared_idx" IS \'kept\'',
        ],
    )


async def test_index_rename_clears_comment(gen_setup: GenerateSetup) -> None:
    """
    An index renamed (same definition) whose source carries a comment but whose target does
    not: RENAME preserves the comment, so COMMENT ... IS NULL must also be emitted, else the
    renamed index keeps the stale comment and the migration does not converge.
    """
    await gen_setup.assert_diff(
        both=["CREATE TABLE person (name text)"],
        src=[
            "CREATE INDEX person_name_old ON person (name)",
            "COMMENT ON INDEX person_name_old IS 'by name'",
        ],
        dst=["CREATE INDEX person_name_new ON person (name)"],
        diff=[
            'ALTER INDEX "public"."person_name_old" RENAME TO "person_name_new"',
            'COMMENT ON INDEX "public"."person_name_new" IS NULL',
        ],
    )


async def test_index_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical name and definition on both sides -> no migration SQL.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (name text)",
            "CREATE INDEX person_name_idx ON person (name)",
        ],
        dst=[
            "CREATE TABLE person (name text)",
            "CREATE INDEX person_name_idx ON person (name)",
        ],
        diff=[],
    )


async def test_index_definition_changed(gen_setup: GenerateSetup) -> None:
    """
    Same name, different definition -> DROP INDEX then CREATE INDEX.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (name text, age integer)",
            "CREATE INDEX person_idx ON person (name)",
        ],
        dst=[
            "CREATE TABLE person (name text, age integer)",
            "CREATE INDEX person_idx ON person (age)",
        ],
        diff=[
            'DROP INDEX "public"."person_idx"',
            "CREATE INDEX person_idx ON public.person USING btree (age)",
        ],
    )


async def test_index_unique(gen_setup: GenerateSetup) -> None:
    """
    Unique index round-trips as CREATE UNIQUE INDEX.
    """
    await gen_setup.assert_diff(
        both=["CREATE TABLE person (name text)"],
        src=[],
        dst=["CREATE UNIQUE INDEX person_name_idx ON person (name)"],
        diff=["CREATE UNIQUE INDEX person_name_idx ON public.person USING btree (name)"],
    )


async def test_index_partial(gen_setup: GenerateSetup) -> None:
    """
    Partial index (WHERE predicate) is created with its predicate.
    """
    await gen_setup.assert_diff(
        both=["CREATE TABLE person (name text)"],
        src=[],
        dst=["CREATE INDEX person_name_idx ON person (name) WHERE name IS NOT NULL"],
        diff=["CREATE INDEX person_name_idx ON public.person USING btree (name) WHERE (name IS NOT NULL)"],
    )


async def test_index_on_created_table(gen_setup: GenerateSetup) -> None:
    """
    Table created on target with an index -> CREATE TABLE then CREATE INDEX.
    """
    await gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE TABLE person (name text)",
            "CREATE INDEX person_name_idx ON person (name)",
        ],
        diff=[
            'CREATE TABLE "public"."person" ("name" text)',
            "CREATE INDEX person_name_idx ON public.person USING btree (name)",
        ],
    )


async def test_index_dropped_with_table(gen_setup: GenerateSetup) -> None:
    """
    Table (with an index) dropped -> DROP TABLE only; the index rides along.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (name text)",
            "CREATE INDEX person_name_idx ON person (name)",
        ],
        dst=[],
        diff=['DROP TABLE "public"."person"'],
    )


async def test_index_constraint_backed_not_created_as_index(gen_setup: GenerateSetup) -> None:
    """
    The indexes backing a PRIMARY KEY / UNIQUE constraint are handled via the
    constraint (ADD CONSTRAINT), never emitted as standalone CREATE INDEX.
    """
    # `id` is NOT NULL on both sides so only the constraint differs, isolating the
    # index behavior from the NOT NULL that a PRIMARY KEY would otherwise imply.
    await gen_setup.assert_diff(
        both=["CREATE TABLE person (id integer NOT NULL, email text)"],
        src=[],
        dst=["ALTER TABLE person ADD PRIMARY KEY (id)", "ALTER TABLE person ADD UNIQUE (email)"],
        diff=[
            'ALTER TABLE "public"."person" ADD CONSTRAINT "person_email_key" UNIQUE (email)',
            'ALTER TABLE "public"."person" ADD CONSTRAINT "person_pkey" PRIMARY KEY (id)',
        ],
    )


async def test_index_comment_added(gen_setup: GenerateSetup) -> None:
    """
    Comment added to an index present on both sides -> COMMENT ON INDEX.
    """
    await gen_setup.assert_diff(
        both=[
            "CREATE TABLE person (name text)",
            "CREATE INDEX person_name_idx ON person (name)",
        ],
        src=[],
        dst=["COMMENT ON INDEX person_name_idx IS 'by name'"],
        diff=['COMMENT ON INDEX "public"."person_name_idx" IS \'by name\''],
    )


async def test_index_comment_removed(gen_setup: GenerateSetup) -> None:
    """
    Comment removed from an index -> COMMENT ON INDEX ... IS NULL.
    """
    await gen_setup.assert_diff(
        both=[
            "CREATE TABLE person (name text)",
            "CREATE INDEX person_name_idx ON person (name)",
        ],
        src=["COMMENT ON INDEX person_name_idx IS 'by name'"],
        dst=[],
        diff=['COMMENT ON INDEX "public"."person_name_idx" IS NULL'],
    )


async def test_index_create_concurrently(gen_setup: GenerateSetup) -> None:
    """
    With index_concurrently, a created index carries CONCURRENTLY.
    """
    await gen_setup.assert_diff(
        both=["CREATE TABLE person (name text)"],
        src=[],
        dst=["CREATE INDEX person_name_idx ON person (name)"],
        diff=["CREATE INDEX CONCURRENTLY person_name_idx ON public.person USING btree (name)"],
        index_concurrently=True,
    )


async def test_index_create_unique_concurrently(gen_setup: GenerateSetup) -> None:
    """
    With index_concurrently, a created unique index carries CONCURRENTLY after UNIQUE.
    """
    await gen_setup.assert_diff(
        both=["CREATE TABLE person (name text)"],
        src=[],
        dst=["CREATE UNIQUE INDEX person_name_idx ON person (name)"],
        diff=["CREATE UNIQUE INDEX CONCURRENTLY person_name_idx ON public.person USING btree (name)"],
        index_concurrently=True,
    )


async def test_index_drop_concurrently(gen_setup: GenerateSetup) -> None:
    """
    With index_concurrently, a dropped index carries CONCURRENTLY.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (name text)",
            "CREATE INDEX person_name_idx ON person (name)",
        ],
        dst=["CREATE TABLE person (name text)"],
        diff=['DROP INDEX CONCURRENTLY "public"."person_name_idx"'],
        index_concurrently=True,
    )


async def test_index_rename_not_concurrent(gen_setup: GenerateSetup) -> None:
    """
    A rename is ALTER INDEX and cannot be CONCURRENTLY; the flag leaves it unchanged.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (name text)",
            "CREATE INDEX person_name_old ON person (name)",
        ],
        dst=[
            "CREATE TABLE person (name text)",
            "CREATE INDEX person_name_new ON person (name)",
        ],
        diff=['ALTER INDEX "public"."person_name_old" RENAME TO "person_name_new"'],
        index_concurrently=True,
    )
