from tests.fixtures.generate_setup import GenerateSetup


def test_index_create(gen_setup: GenerateSetup) -> None:
    """
    Index present in target but missing in source -> CREATE INDEX.
    """
    gen_setup.execute_both("CREATE TABLE person (name text)")
    gen_setup.dst.execute("CREATE INDEX person_name_idx ON person (name)")

    gen_setup.assert_migration_sql("CREATE INDEX person_name_idx ON public.person USING btree (name);")


def test_index_drop(gen_setup: GenerateSetup) -> None:
    """
    Index present in source but missing in target -> DROP INDEX.
    """
    gen_setup.src.execute("CREATE TABLE person (name text)")
    gen_setup.src.execute("CREATE INDEX person_name_idx ON person (name)")
    gen_setup.dst.execute("CREATE TABLE person (name text)")

    gen_setup.assert_migration_sql('DROP INDEX "public"."person_name_idx";')


def test_index_rename(gen_setup: GenerateSetup) -> None:
    """
    Same definition on both sides, only the name differs -> ALTER INDEX RENAME.
    """
    gen_setup.src.execute("CREATE TABLE person (name text)")
    gen_setup.src.execute("CREATE INDEX person_name_old ON person (name)")
    gen_setup.dst.execute("CREATE TABLE person (name text)")
    gen_setup.dst.execute("CREATE INDEX person_name_new ON person (name)")

    gen_setup.assert_migration_sql('ALTER INDEX "public"."person_name_old" RENAME TO "person_name_new";')


def test_index_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical name and definition on both sides -> no migration SQL.
    """
    gen_setup.src.execute("CREATE TABLE person (name text)")
    gen_setup.src.execute("CREATE INDEX person_name_idx ON person (name)")
    gen_setup.dst.execute("CREATE TABLE person (name text)")
    gen_setup.dst.execute("CREATE INDEX person_name_idx ON person (name)")

    gen_setup.assert_migration_sql("")


def test_index_definition_changed(gen_setup: GenerateSetup) -> None:
    """
    Same name, different definition -> DROP INDEX then CREATE INDEX.
    """
    gen_setup.src.execute("CREATE TABLE person (name text, age integer)")
    gen_setup.src.execute("CREATE INDEX person_idx ON person (name)")
    gen_setup.dst.execute("CREATE TABLE person (name text, age integer)")
    gen_setup.dst.execute("CREATE INDEX person_idx ON person (age)")

    gen_setup.assert_migration_sql(
        [
            'DROP INDEX "public"."person_idx";',
            "CREATE INDEX person_idx ON public.person USING btree (age);",
        ]
    )


def test_index_unique(gen_setup: GenerateSetup) -> None:
    """
    Unique index round-trips as CREATE UNIQUE INDEX.
    """
    gen_setup.execute_both("CREATE TABLE person (name text)")
    gen_setup.dst.execute("CREATE UNIQUE INDEX person_name_idx ON person (name)")

    gen_setup.assert_migration_sql("CREATE UNIQUE INDEX person_name_idx ON public.person USING btree (name);")


def test_index_partial(gen_setup: GenerateSetup) -> None:
    """
    Partial index (WHERE predicate) is created with its predicate.
    """
    gen_setup.execute_both("CREATE TABLE person (name text)")
    gen_setup.dst.execute("CREATE INDEX person_name_idx ON person (name) WHERE name IS NOT NULL")

    gen_setup.assert_migration_sql(
        "CREATE INDEX person_name_idx ON public.person USING btree (name) WHERE (name IS NOT NULL);"
    )


def test_index_on_created_table(gen_setup: GenerateSetup) -> None:
    """
    Table created on target with an index -> CREATE TABLE then CREATE INDEX.
    """
    gen_setup.dst.execute("CREATE TABLE person (name text)")
    gen_setup.dst.execute("CREATE INDEX person_name_idx ON person (name)")

    gen_setup.assert_migration_sql(
        [
            'CREATE TABLE "public"."person" ("name" text);',
            "CREATE INDEX person_name_idx ON public.person USING btree (name);",
        ]
    )


def test_index_dropped_with_table(gen_setup: GenerateSetup) -> None:
    """
    Table (with an index) dropped -> DROP TABLE only; the index rides along.
    """
    gen_setup.src.execute("CREATE TABLE person (name text)")
    gen_setup.src.execute("CREATE INDEX person_name_idx ON person (name)")

    gen_setup.assert_migration_sql('DROP TABLE "public"."person";')


def test_index_constraint_backed_not_created_as_index(gen_setup: GenerateSetup) -> None:
    """
    The indexes backing a PRIMARY KEY / UNIQUE constraint are handled via the
    constraint (ADD CONSTRAINT), never emitted as standalone CREATE INDEX.
    """
    # `id` is NOT NULL on both sides so only the constraint differs, isolating the
    # index behavior from the NOT NULL that a PRIMARY KEY would otherwise imply.
    gen_setup.src.execute("CREATE TABLE person (id integer NOT NULL, email text)")
    gen_setup.dst.execute("CREATE TABLE person (id integer NOT NULL, email text)")
    gen_setup.dst.execute("ALTER TABLE person ADD PRIMARY KEY (id)")
    gen_setup.dst.execute("ALTER TABLE person ADD UNIQUE (email)")

    gen_setup.assert_migration_sql(
        [
            'ALTER TABLE "public"."person" ADD CONSTRAINT "person_email_key" UNIQUE (email);',
            'ALTER TABLE "public"."person" ADD CONSTRAINT "person_pkey" PRIMARY KEY (id);',
        ]
    )


def test_index_comment_added(gen_setup: GenerateSetup) -> None:
    """
    Comment added to an index present on both sides -> COMMENT ON INDEX.
    """
    gen_setup.execute_both("CREATE TABLE person (name text)")
    gen_setup.execute_both("CREATE INDEX person_name_idx ON person (name)")
    gen_setup.dst.execute("COMMENT ON INDEX person_name_idx IS 'by name'")

    gen_setup.assert_migration_sql('COMMENT ON INDEX "public"."person_name_idx" IS \'by name\';')


def test_index_comment_removed(gen_setup: GenerateSetup) -> None:
    """
    Comment removed from an index -> COMMENT ON INDEX ... IS NULL.
    """
    gen_setup.execute_both("CREATE TABLE person (name text)")
    gen_setup.execute_both("CREATE INDEX person_name_idx ON person (name)")
    gen_setup.src.execute("COMMENT ON INDEX person_name_idx IS 'by name'")

    gen_setup.assert_migration_sql('COMMENT ON INDEX "public"."person_name_idx" IS NULL;')
