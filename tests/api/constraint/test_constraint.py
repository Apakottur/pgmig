from tests.api.generate_setup import GenerateSetup


def test_exclusion_constraint_raises_not_supported(gen_setup: GenerateSetup) -> None:
    """
    An EXCLUDE constraint (pg_constraint contype 'x') is not modelled yet and must raise
    rather than be silently dropped by the constraint query's contype filter.
    """
    gen_setup.assert_unsupported(
        src=[],
        dst=["CREATE TABLE room (during int4range, EXCLUDE USING gist (during WITH &&))"],
        match=r"exclusion constraint .* is not supported",
    )


def test_constraint_add_primary_key(gen_setup: GenerateSetup) -> None:
    """
    Primary key present in target but missing in source -> ADD CONSTRAINT.
    """
    gen_setup.assert_diff(
        both=["CREATE TABLE person (id integer NOT NULL)"],
        src=[],
        dst=["ALTER TABLE person ADD CONSTRAINT person_pkey PRIMARY KEY (id)"],
        diff=['ALTER TABLE "public"."person" ADD CONSTRAINT "person_pkey" PRIMARY KEY (id)'],
    )


def test_constraint_drop_primary_key(gen_setup: GenerateSetup) -> None:
    """
    Primary key present in source but missing in target -> DROP CONSTRAINT.
    """
    gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (id integer NOT NULL)",
            "ALTER TABLE person ADD CONSTRAINT person_pkey PRIMARY KEY (id)",
        ],
        dst=["CREATE TABLE person (id integer NOT NULL)"],
        diff=['ALTER TABLE "public"."person" DROP CONSTRAINT "person_pkey"'],
    )


def test_constraint_add_unique(gen_setup: GenerateSetup) -> None:
    """
    Unique constraint present in target but missing in source -> ADD CONSTRAINT.
    """
    gen_setup.assert_diff(
        both=["CREATE TABLE person (email text)"],
        src=[],
        dst=["ALTER TABLE person ADD CONSTRAINT person_email_key UNIQUE (email)"],
        diff=['ALTER TABLE "public"."person" ADD CONSTRAINT "person_email_key" UNIQUE (email)'],
    )


def test_constraint_drop_unique(gen_setup: GenerateSetup) -> None:
    """
    Unique constraint present in source but missing in target -> DROP CONSTRAINT.
    """
    gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (email text)",
            "ALTER TABLE person ADD CONSTRAINT person_email_key UNIQUE (email)",
        ],
        dst=["CREATE TABLE person (email text)"],
        diff=['ALTER TABLE "public"."person" DROP CONSTRAINT "person_email_key"'],
    )


def test_constraint_rename(gen_setup: GenerateSetup) -> None:
    """
    Same definition on both sides, only the name differs -> RENAME CONSTRAINT.
    """
    gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (email text)",
            "ALTER TABLE person ADD CONSTRAINT person_email_old UNIQUE (email)",
        ],
        dst=[
            "CREATE TABLE person (email text)",
            "ALTER TABLE person ADD CONSTRAINT person_email_new UNIQUE (email)",
        ],
        diff=['ALTER TABLE "public"."person" RENAME CONSTRAINT "person_email_old" TO "person_email_new"'],
    )


def test_constraint_rename_clears_comment(gen_setup: GenerateSetup) -> None:
    """
    A constraint renamed (same definition) whose source carries a comment but whose target
    does not: RENAME preserves the comment, so COMMENT ... IS NULL must also be emitted, else
    the migration does not converge.
    """
    gen_setup.assert_diff(
        both=["CREATE TABLE person (email text)"],
        src=[
            "ALTER TABLE person ADD CONSTRAINT person_email_old UNIQUE (email)",
            "COMMENT ON CONSTRAINT person_email_old ON person IS 'unique email'",
        ],
        dst=["ALTER TABLE person ADD CONSTRAINT person_email_new UNIQUE (email)"],
        diff=[
            'ALTER TABLE "public"."person" RENAME CONSTRAINT "person_email_old" TO "person_email_new"',
            'COMMENT ON CONSTRAINT "person_email_new" ON "public"."person" IS NULL',
        ],
    )


def test_constraint_definition_changed(gen_setup: GenerateSetup) -> None:
    """
    Same name, different definition -> DROP CONSTRAINT then ADD CONSTRAINT.
    """
    gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (email text, phone text)",
            "ALTER TABLE person ADD CONSTRAINT person_key UNIQUE (email)",
        ],
        dst=[
            "CREATE TABLE person (email text, phone text)",
            "ALTER TABLE person ADD CONSTRAINT person_key UNIQUE (phone)",
        ],
        diff=[
            'ALTER TABLE "public"."person" DROP CONSTRAINT "person_key"',
            'ALTER TABLE "public"."person" ADD CONSTRAINT "person_key" UNIQUE (phone)',
        ],
    )


def test_constraint_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Same name and definition on both sides -> no migration SQL.
    """
    gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (email text)",
            "ALTER TABLE person ADD CONSTRAINT person_email_key UNIQUE (email)",
        ],
        dst=[
            "CREATE TABLE person (email text)",
            "ALTER TABLE person ADD CONSTRAINT person_email_key UNIQUE (email)",
        ],
        diff=[],
    )


def test_constraint_primary_key_suppresses_set_not_null(gen_setup: GenerateSetup) -> None:
    """
    Adding a primary key on a source-nullable column emits only ADD CONSTRAINT;
    the redundant SET NOT NULL is suppressed.
    """
    gen_setup.assert_diff(
        src=["CREATE TABLE person (id integer)"],
        dst=[
            "CREATE TABLE person (id integer NOT NULL)",
            "ALTER TABLE person ADD CONSTRAINT person_pkey PRIMARY KEY (id)",
        ],
        diff=['ALTER TABLE "public"."person" ADD CONSTRAINT "person_pkey" PRIMARY KEY (id)'],
    )


def test_constraint_dropped_with_table(gen_setup: GenerateSetup) -> None:
    """
    Table (with a constraint) dropped -> DROP TABLE only; the constraint rides along.
    """
    gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (id integer NOT NULL)",
            "ALTER TABLE person ADD CONSTRAINT person_pkey PRIMARY KEY (id)",
        ],
        dst=[],
        diff=['DROP TABLE "public"."person"'],
    )


def test_constraint_add_check(gen_setup: GenerateSetup) -> None:
    """
    Check constraint present in target but missing in source -> ADD CONSTRAINT.
    """
    gen_setup.assert_diff(
        src=["CREATE TABLE person (age integer)"],
        dst=[
            "CREATE TABLE person (age integer)",
            "ALTER TABLE person ADD CONSTRAINT person_age_check CHECK (age > 0)",
        ],
        diff=['ALTER TABLE "public"."person" ADD CONSTRAINT "person_age_check" CHECK ((age > 0))'],
    )


def test_constraint_drop_check(gen_setup: GenerateSetup) -> None:
    """
    Check constraint present in source but missing in target -> DROP CONSTRAINT.
    """
    gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (age integer)",
            "ALTER TABLE person ADD CONSTRAINT person_age_check CHECK (age > 0)",
        ],
        dst=["CREATE TABLE person (age integer)"],
        diff=['ALTER TABLE "public"."person" DROP CONSTRAINT "person_age_check"'],
    )


def test_constraint_rename_check(gen_setup: GenerateSetup) -> None:
    """
    Same check definition on both sides, only the name differs -> RENAME CONSTRAINT.
    """
    gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (age integer)",
            "ALTER TABLE person ADD CONSTRAINT person_age_old CHECK (age > 0)",
        ],
        dst=[
            "CREATE TABLE person (age integer)",
            "ALTER TABLE person ADD CONSTRAINT person_age_new CHECK (age > 0)",
        ],
        diff=['ALTER TABLE "public"."person" RENAME CONSTRAINT "person_age_old" TO "person_age_new"'],
    )


def test_constraint_check_definition_changed(gen_setup: GenerateSetup) -> None:
    """
    Same name, different check expression -> DROP CONSTRAINT then ADD CONSTRAINT.
    """
    gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (age integer)",
            "ALTER TABLE person ADD CONSTRAINT person_age_check CHECK (age > 0)",
        ],
        dst=[
            "CREATE TABLE person (age integer)",
            "ALTER TABLE person ADD CONSTRAINT person_age_check CHECK (age > 18)",
        ],
        diff=[
            'ALTER TABLE "public"."person" DROP CONSTRAINT "person_age_check"',
            'ALTER TABLE "public"."person" ADD CONSTRAINT "person_age_check" CHECK ((age > 18))',
        ],
    )


def test_constraint_check_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Same check name and definition on both sides -> no migration SQL.
    """
    gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (age integer)",
            "ALTER TABLE person ADD CONSTRAINT person_age_check CHECK (age > 0)",
        ],
        dst=[
            "CREATE TABLE person (age integer)",
            "ALTER TABLE person ADD CONSTRAINT person_age_check CHECK (age > 0)",
        ],
        diff=[],
    )


def test_constraint_comment_added(gen_setup: GenerateSetup) -> None:
    """
    Comment added to a constraint present on both sides -> COMMENT ON CONSTRAINT.
    """
    gen_setup.assert_diff(
        both=[
            "CREATE TABLE person (email text)",
            "ALTER TABLE person ADD CONSTRAINT person_email_key UNIQUE (email)",
        ],
        src=[],
        dst=["COMMENT ON CONSTRAINT person_email_key ON person IS 'unique email'"],
        diff=['COMMENT ON CONSTRAINT "person_email_key" ON "public"."person" IS \'unique email\''],
    )


def test_foreign_key_comment_added(gen_setup: GenerateSetup) -> None:
    """
    Comment added to a foreign key -> COMMENT ON CONSTRAINT.
    """
    gen_setup.assert_diff(
        both=[
            "CREATE TABLE team (id integer NOT NULL, CONSTRAINT team_pkey PRIMARY KEY (id))",
            "CREATE TABLE person (team_id integer)",
            "ALTER TABLE person ADD CONSTRAINT person_team_fkey FOREIGN KEY (team_id) REFERENCES team (id)",
        ],
        src=[],
        dst=["COMMENT ON CONSTRAINT person_team_fkey ON person IS 'team ref'"],
        diff=['COMMENT ON CONSTRAINT "person_team_fkey" ON "public"."person" IS \'team ref\''],
    )
