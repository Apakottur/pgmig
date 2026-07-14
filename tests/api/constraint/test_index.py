from tests.api.generate_setup import GenerateSetup


def test_index_create(gen_setup: GenerateSetup) -> None:
    """
    Index present in target but missing in source -> CREATE INDEX.
    """
    gen_setup.assert_diff(
        both=["CREATE TABLE person (name text)"],
        src=[],
        dst=["CREATE INDEX person_name_idx ON person (name)"],
        diff=["CREATE INDEX person_name_idx ON public.person USING btree (name)"],
    )


def test_index_drop(gen_setup: GenerateSetup) -> None:
    """
    Index present in source but missing in target -> DROP INDEX.
    """
    gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (name text)",
            "CREATE INDEX person_name_idx ON person (name)",
        ],
        dst=["CREATE TABLE person (name text)"],
        diff=['DROP INDEX "public"."person_name_idx"'],
    )


def test_index_rename(gen_setup: GenerateSetup) -> None:
    """
    Same definition on both sides, only the name differs -> ALTER INDEX RENAME.
    """
    gen_setup.assert_diff(
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


def test_index_rename_clears_comment(gen_setup: GenerateSetup) -> None:
    """
    An index renamed (same definition) whose source carries a comment but whose target does
    not: RENAME preserves the comment, so COMMENT ... IS NULL must also be emitted, else the
    renamed index keeps the stale comment and the migration does not converge.
    """
    gen_setup.assert_diff(
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


def test_index_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical name and definition on both sides -> no migration SQL.
    """
    gen_setup.assert_diff(
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


def test_index_definition_changed(gen_setup: GenerateSetup) -> None:
    """
    Same name, different definition -> DROP INDEX then CREATE INDEX.
    """
    gen_setup.assert_diff(
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


def test_index_unique(gen_setup: GenerateSetup) -> None:
    """
    Unique index round-trips as CREATE UNIQUE INDEX.
    """
    gen_setup.assert_diff(
        both=["CREATE TABLE person (name text)"],
        src=[],
        dst=["CREATE UNIQUE INDEX person_name_idx ON person (name)"],
        diff=["CREATE UNIQUE INDEX person_name_idx ON public.person USING btree (name)"],
    )


def test_index_partial(gen_setup: GenerateSetup) -> None:
    """
    Partial index (WHERE predicate) is created with its predicate.
    """
    gen_setup.assert_diff(
        both=["CREATE TABLE person (name text)"],
        src=[],
        dst=["CREATE INDEX person_name_idx ON person (name) WHERE name IS NOT NULL"],
        diff=["CREATE INDEX person_name_idx ON public.person USING btree (name) WHERE (name IS NOT NULL)"],
    )


def test_index_on_created_table(gen_setup: GenerateSetup) -> None:
    """
    Table created on target with an index -> CREATE TABLE then CREATE INDEX.
    """
    gen_setup.assert_diff(
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


def test_index_dropped_with_table(gen_setup: GenerateSetup) -> None:
    """
    Table (with an index) dropped -> DROP TABLE only; the index rides along.
    """
    gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (name text)",
            "CREATE INDEX person_name_idx ON person (name)",
        ],
        dst=[],
        diff=['DROP TABLE "public"."person"'],
    )


def test_index_constraint_backed_not_created_as_index(gen_setup: GenerateSetup) -> None:
    """
    The indexes backing a PRIMARY KEY / UNIQUE constraint are handled via the
    constraint (ADD CONSTRAINT), never emitted as standalone CREATE INDEX.
    """
    # `id` is NOT NULL on both sides so only the constraint differs, isolating the
    # index behavior from the NOT NULL that a PRIMARY KEY would otherwise imply.
    gen_setup.assert_diff(
        both=["CREATE TABLE person (id integer NOT NULL, email text)"],
        src=[],
        dst=["ALTER TABLE person ADD PRIMARY KEY (id)", "ALTER TABLE person ADD UNIQUE (email)"],
        diff=[
            'ALTER TABLE "public"."person" ADD CONSTRAINT "person_email_key" UNIQUE (email)',
            'ALTER TABLE "public"."person" ADD CONSTRAINT "person_pkey" PRIMARY KEY (id)',
        ],
    )


def test_index_comment_added(gen_setup: GenerateSetup) -> None:
    """
    Comment added to an index present on both sides -> COMMENT ON INDEX.
    """
    gen_setup.assert_diff(
        both=[
            "CREATE TABLE person (name text)",
            "CREATE INDEX person_name_idx ON person (name)",
        ],
        src=[],
        dst=["COMMENT ON INDEX person_name_idx IS 'by name'"],
        diff=['COMMENT ON INDEX "public"."person_name_idx" IS \'by name\''],
    )


def test_index_comment_removed(gen_setup: GenerateSetup) -> None:
    """
    Comment removed from an index -> COMMENT ON INDEX ... IS NULL.
    """
    gen_setup.assert_diff(
        both=[
            "CREATE TABLE person (name text)",
            "CREATE INDEX person_name_idx ON person (name)",
        ],
        src=["COMMENT ON INDEX person_name_idx IS 'by name'"],
        dst=[],
        diff=['COMMENT ON INDEX "public"."person_name_idx" IS NULL'],
    )


def test_index_create_concurrently(gen_setup: GenerateSetup) -> None:
    """
    With index_concurrently, a created index carries CONCURRENTLY.
    """
    gen_setup.assert_diff(
        both=["CREATE TABLE person (name text)"],
        src=[],
        dst=["CREATE INDEX person_name_idx ON person (name)"],
        diff=["CREATE INDEX CONCURRENTLY person_name_idx ON public.person USING btree (name)"],
        index_concurrently=True,
    )


def test_index_create_unique_concurrently(gen_setup: GenerateSetup) -> None:
    """
    With index_concurrently, a created unique index carries CONCURRENTLY after UNIQUE.
    """
    gen_setup.assert_diff(
        both=["CREATE TABLE person (name text)"],
        src=[],
        dst=["CREATE UNIQUE INDEX person_name_idx ON person (name)"],
        diff=["CREATE UNIQUE INDEX CONCURRENTLY person_name_idx ON public.person USING btree (name)"],
        index_concurrently=True,
    )


def test_index_drop_concurrently(gen_setup: GenerateSetup) -> None:
    """
    With index_concurrently, a dropped index carries CONCURRENTLY.
    """
    gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (name text)",
            "CREATE INDEX person_name_idx ON person (name)",
        ],
        dst=["CREATE TABLE person (name text)"],
        diff=['DROP INDEX CONCURRENTLY "public"."person_name_idx"'],
        index_concurrently=True,
    )


def test_index_rename_not_concurrent(gen_setup: GenerateSetup) -> None:
    """
    A rename is ALTER INDEX and cannot be CONCURRENTLY; the flag leaves it unchanged.
    """
    gen_setup.assert_diff(
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
