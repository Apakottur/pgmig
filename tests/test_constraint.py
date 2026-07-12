from tests.fixtures.generate_setup import GenerateSetup


def test_constraint_add_primary_key(gen_setup: GenerateSetup) -> None:
    """
    Primary key present in target but missing in source -> ADD CONSTRAINT.
    """
    gen_setup.execute_both("CREATE TABLE person (id integer NOT NULL)")
    gen_setup.dst.execute("ALTER TABLE person ADD CONSTRAINT person_pkey PRIMARY KEY (id)")

    gen_setup.assert_migration_sql('ALTER TABLE "public"."person" ADD CONSTRAINT "person_pkey" PRIMARY KEY (id);')


def test_constraint_drop_primary_key(gen_setup: GenerateSetup) -> None:
    """
    Primary key present in source but missing in target -> DROP CONSTRAINT.
    """
    gen_setup.src.execute("CREATE TABLE person (id integer NOT NULL)")
    gen_setup.src.execute("ALTER TABLE person ADD CONSTRAINT person_pkey PRIMARY KEY (id)")
    gen_setup.dst.execute("CREATE TABLE person (id integer NOT NULL)")

    gen_setup.assert_migration_sql('ALTER TABLE "public"."person" DROP CONSTRAINT "person_pkey";')


def test_constraint_add_unique(gen_setup: GenerateSetup) -> None:
    """
    Unique constraint present in target but missing in source -> ADD CONSTRAINT.
    """
    gen_setup.execute_both("CREATE TABLE person (email text)")
    gen_setup.dst.execute("ALTER TABLE person ADD CONSTRAINT person_email_key UNIQUE (email)")

    gen_setup.assert_migration_sql('ALTER TABLE "public"."person" ADD CONSTRAINT "person_email_key" UNIQUE (email);')


def test_constraint_drop_unique(gen_setup: GenerateSetup) -> None:
    """
    Unique constraint present in source but missing in target -> DROP CONSTRAINT.
    """
    gen_setup.src.execute("CREATE TABLE person (email text)")
    gen_setup.src.execute("ALTER TABLE person ADD CONSTRAINT person_email_key UNIQUE (email)")
    gen_setup.dst.execute("CREATE TABLE person (email text)")

    gen_setup.assert_migration_sql('ALTER TABLE "public"."person" DROP CONSTRAINT "person_email_key";')


def test_constraint_rename(gen_setup: GenerateSetup) -> None:
    """
    Same definition on both sides, only the name differs -> RENAME CONSTRAINT.
    """
    gen_setup.src.execute("CREATE TABLE person (email text)")
    gen_setup.src.execute("ALTER TABLE person ADD CONSTRAINT person_email_old UNIQUE (email)")
    gen_setup.dst.execute("CREATE TABLE person (email text)")
    gen_setup.dst.execute("ALTER TABLE person ADD CONSTRAINT person_email_new UNIQUE (email)")

    gen_setup.assert_migration_sql(
        'ALTER TABLE "public"."person" RENAME CONSTRAINT "person_email_old" TO "person_email_new";'
    )


def test_constraint_definition_changed(gen_setup: GenerateSetup) -> None:
    """
    Same name, different definition -> DROP CONSTRAINT then ADD CONSTRAINT.
    """
    gen_setup.src.execute("CREATE TABLE person (email text, phone text)")
    gen_setup.src.execute("ALTER TABLE person ADD CONSTRAINT person_key UNIQUE (email)")
    gen_setup.dst.execute("CREATE TABLE person (email text, phone text)")
    gen_setup.dst.execute("ALTER TABLE person ADD CONSTRAINT person_key UNIQUE (phone)")

    gen_setup.assert_migration_sql(
        [
            'ALTER TABLE "public"."person" DROP CONSTRAINT "person_key";',
            'ALTER TABLE "public"."person" ADD CONSTRAINT "person_key" UNIQUE (phone);',
        ]
    )


def test_constraint_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Same name and definition on both sides -> no migration SQL.
    """
    gen_setup.src.execute("CREATE TABLE person (email text)")
    gen_setup.src.execute("ALTER TABLE person ADD CONSTRAINT person_email_key UNIQUE (email)")
    gen_setup.dst.execute("CREATE TABLE person (email text)")
    gen_setup.dst.execute("ALTER TABLE person ADD CONSTRAINT person_email_key UNIQUE (email)")

    gen_setup.assert_migration_sql("")


def test_constraint_primary_key_suppresses_set_not_null(gen_setup: GenerateSetup) -> None:
    """
    Adding a primary key on a source-nullable column emits only ADD CONSTRAINT;
    the redundant SET NOT NULL is suppressed.
    """
    gen_setup.src.execute("CREATE TABLE person (id integer)")
    gen_setup.dst.execute("CREATE TABLE person (id integer NOT NULL)")
    gen_setup.dst.execute("ALTER TABLE person ADD CONSTRAINT person_pkey PRIMARY KEY (id)")

    gen_setup.assert_migration_sql('ALTER TABLE "public"."person" ADD CONSTRAINT "person_pkey" PRIMARY KEY (id);')


def test_constraint_dropped_with_table(gen_setup: GenerateSetup) -> None:
    """
    Table (with a constraint) dropped -> DROP TABLE only; the constraint rides along.
    """
    gen_setup.src.execute("CREATE TABLE person (id integer NOT NULL)")
    gen_setup.src.execute("ALTER TABLE person ADD CONSTRAINT person_pkey PRIMARY KEY (id)")

    gen_setup.assert_migration_sql('DROP TABLE "public"."person";')


def test_constraint_add_check(gen_setup: GenerateSetup) -> None:
    """
    Check constraint present in target but missing in source -> ADD CONSTRAINT.
    """
    gen_setup.src.execute("CREATE TABLE person (age integer)")
    gen_setup.dst.execute("CREATE TABLE person (age integer)")
    gen_setup.dst.execute("ALTER TABLE person ADD CONSTRAINT person_age_check CHECK (age > 0)")

    gen_setup.assert_migration_sql('ALTER TABLE "public"."person" ADD CONSTRAINT "person_age_check" CHECK ((age > 0));')


def test_constraint_drop_check(gen_setup: GenerateSetup) -> None:
    """
    Check constraint present in source but missing in target -> DROP CONSTRAINT.
    """
    gen_setup.src.execute("CREATE TABLE person (age integer)")
    gen_setup.src.execute("ALTER TABLE person ADD CONSTRAINT person_age_check CHECK (age > 0)")
    gen_setup.dst.execute("CREATE TABLE person (age integer)")

    gen_setup.assert_migration_sql('ALTER TABLE "public"."person" DROP CONSTRAINT "person_age_check";')


def test_constraint_rename_check(gen_setup: GenerateSetup) -> None:
    """
    Same check definition on both sides, only the name differs -> RENAME CONSTRAINT.
    """
    gen_setup.src.execute("CREATE TABLE person (age integer)")
    gen_setup.src.execute("ALTER TABLE person ADD CONSTRAINT person_age_old CHECK (age > 0)")
    gen_setup.dst.execute("CREATE TABLE person (age integer)")
    gen_setup.dst.execute("ALTER TABLE person ADD CONSTRAINT person_age_new CHECK (age > 0)")

    gen_setup.assert_migration_sql(
        'ALTER TABLE "public"."person" RENAME CONSTRAINT "person_age_old" TO "person_age_new";'
    )


def test_constraint_check_definition_changed(gen_setup: GenerateSetup) -> None:
    """
    Same name, different check expression -> DROP CONSTRAINT then ADD CONSTRAINT.
    """
    gen_setup.src.execute("CREATE TABLE person (age integer)")
    gen_setup.src.execute("ALTER TABLE person ADD CONSTRAINT person_age_check CHECK (age > 0)")
    gen_setup.dst.execute("CREATE TABLE person (age integer)")
    gen_setup.dst.execute("ALTER TABLE person ADD CONSTRAINT person_age_check CHECK (age > 18)")

    gen_setup.assert_migration_sql(
        [
            'ALTER TABLE "public"."person" DROP CONSTRAINT "person_age_check";',
            'ALTER TABLE "public"."person" ADD CONSTRAINT "person_age_check" CHECK ((age > 18));',
        ]
    )


def test_constraint_check_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Same check name and definition on both sides -> no migration SQL.
    """
    gen_setup.src.execute("CREATE TABLE person (age integer)")
    gen_setup.src.execute("ALTER TABLE person ADD CONSTRAINT person_age_check CHECK (age > 0)")
    gen_setup.dst.execute("CREATE TABLE person (age integer)")
    gen_setup.dst.execute("ALTER TABLE person ADD CONSTRAINT person_age_check CHECK (age > 0)")

    gen_setup.assert_migration_sql("")
