from tests.api.generate_setup import GenerateSetup


def _setup_tables(gen_setup: GenerateSetup) -> None:
    """
    Create a referenced table (with a primary key) and a referencing table on both sides.
    """
    gen_setup.execute_both("CREATE TABLE team (id integer NOT NULL, CONSTRAINT team_pkey PRIMARY KEY (id))")
    gen_setup.execute_both("CREATE TABLE person (team_id integer)")


def test_foreign_key_add(gen_setup: GenerateSetup) -> None:
    """
    Foreign key present in target but missing in source -> ADD CONSTRAINT.
    """
    _setup_tables(gen_setup)
    gen_setup.dst.execute(
        "ALTER TABLE person ADD CONSTRAINT person_team_fkey FOREIGN KEY (team_id) REFERENCES team (id)"
    )

    gen_setup.assert_migration_sql(
        'ALTER TABLE "public"."person" ADD CONSTRAINT "person_team_fkey" FOREIGN KEY (team_id) REFERENCES public.team(id);'
    )


def test_foreign_key_drop(gen_setup: GenerateSetup) -> None:
    """
    Foreign key present in source but missing in target -> DROP CONSTRAINT.
    """
    _setup_tables(gen_setup)
    gen_setup.src.execute(
        "ALTER TABLE person ADD CONSTRAINT person_team_fkey FOREIGN KEY (team_id) REFERENCES team (id)"
    )

    gen_setup.assert_migration_sql('ALTER TABLE "public"."person" DROP CONSTRAINT "person_team_fkey";')


def test_foreign_key_rename(gen_setup: GenerateSetup) -> None:
    """
    Same definition on both sides, only the name differs -> RENAME CONSTRAINT.
    """
    _setup_tables(gen_setup)
    gen_setup.src.execute(
        "ALTER TABLE person ADD CONSTRAINT person_team_old FOREIGN KEY (team_id) REFERENCES team (id)"
    )
    gen_setup.dst.execute(
        "ALTER TABLE person ADD CONSTRAINT person_team_new FOREIGN KEY (team_id) REFERENCES team (id)"
    )

    gen_setup.assert_migration_sql(
        'ALTER TABLE "public"."person" RENAME CONSTRAINT "person_team_old" TO "person_team_new";'
    )


def test_foreign_key_definition_changed(gen_setup: GenerateSetup) -> None:
    """
    Same name, different definition -> DROP CONSTRAINT then ADD CONSTRAINT.
    """
    _setup_tables(gen_setup)
    gen_setup.src.execute(
        "ALTER TABLE person ADD CONSTRAINT person_team_fkey FOREIGN KEY (team_id) REFERENCES team (id)"
    )
    gen_setup.dst.execute(
        "ALTER TABLE person ADD CONSTRAINT person_team_fkey FOREIGN KEY (team_id) REFERENCES team (id) ON DELETE CASCADE"
    )

    gen_setup.assert_migration_sql(
        [
            'ALTER TABLE "public"."person" DROP CONSTRAINT "person_team_fkey";',
            'ALTER TABLE "public"."person" ADD CONSTRAINT "person_team_fkey" '
            "FOREIGN KEY (team_id) REFERENCES public.team(id) ON DELETE CASCADE;",
        ]
    )


def test_foreign_key_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical foreign key on both sides -> no migration SQL.
    """
    _setup_tables(gen_setup)
    gen_setup.execute_both(
        "ALTER TABLE person ADD CONSTRAINT person_team_fkey FOREIGN KEY (team_id) REFERENCES team (id)"
    )

    gen_setup.assert_migration_sql("")


def test_foreign_key_add_ordered_after_referenced_pk(gen_setup: GenerateSetup) -> None:
    """
    Creating referenced and referencing tables together: the referenced PRIMARY KEY
    is added before the FOREIGN KEY, and both come after the CREATE TABLEs.
    """
    gen_setup.assert_diff(
        src=[],
        dst=[
            "CREATE TABLE team (id integer NOT NULL, CONSTRAINT team_pkey PRIMARY KEY (id))",
            "CREATE TABLE person (team_id integer)",
            "ALTER TABLE person ADD CONSTRAINT person_team_fkey FOREIGN KEY (team_id) REFERENCES team (id)",
        ],
        diff=[
            'CREATE TABLE "public"."person" ("team_id" integer)',
            'CREATE TABLE "public"."team" ("id" integer NOT NULL)',
            'ALTER TABLE "public"."team" ADD CONSTRAINT "team_pkey" PRIMARY KEY (id)',
            'ALTER TABLE "public"."person" ADD CONSTRAINT "person_team_fkey" FOREIGN KEY (team_id) REFERENCES public.team(id)',
        ],
    )


def test_foreign_key_drop_ordered_before_referenced_table(gen_setup: GenerateSetup) -> None:
    """
    Dropping a referenced table: the FOREIGN KEY is dropped before the DROP TABLE.
    """
    gen_setup.assert_diff(
        src=[
            "CREATE TABLE team (id integer NOT NULL, CONSTRAINT team_pkey PRIMARY KEY (id))",
            "CREATE TABLE person (team_id integer)",
            "ALTER TABLE person ADD CONSTRAINT person_team_fkey FOREIGN KEY (team_id) REFERENCES team (id)",
        ],
        dst=["CREATE TABLE person (team_id integer)"],
        diff=[
            'ALTER TABLE "public"."person" DROP CONSTRAINT "person_team_fkey"',
            'DROP TABLE "public"."team"',
        ],
    )


def test_foreign_key_dropped_with_its_own_table_before_referenced_table(gen_setup: GenerateSetup) -> None:
    """
    Both the referencing table and the referenced table are dropped: the FOREIGN KEY
    must be dropped before either DROP TABLE, otherwise Postgres rejects dropping the
    referenced table while the referencing table's constraint still depends on it.
    """
    gen_setup.assert_diff(
        src=[
            "CREATE TABLE team (id integer NOT NULL, CONSTRAINT team_pkey PRIMARY KEY (id))",
            "CREATE TABLE person (team_id integer)",
            "ALTER TABLE person ADD CONSTRAINT person_team_fkey FOREIGN KEY (team_id) REFERENCES team (id)",
        ],
        dst=[],
        diff=[
            'ALTER TABLE "public"."person" DROP CONSTRAINT "person_team_fkey"',
            'DROP TABLE "public"."person"',
            'DROP TABLE "public"."team"',
        ],
    )
