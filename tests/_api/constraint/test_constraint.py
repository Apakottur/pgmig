from tests._api.generate_setup import GenerateSetup


async def test_constraint_add_primary_key(gen_setup: GenerateSetup) -> None:
    """
    Primary key present in target but missing in source -> ADD CONSTRAINT.
    """
    await gen_setup.assert_diff(
        both=["CREATE TABLE person (id integer NOT NULL)"],
        src=[],
        dst=["ALTER TABLE person ADD CONSTRAINT person_pkey PRIMARY KEY (id)"],
        diff=['ALTER TABLE "public"."person" ADD CONSTRAINT "person_pkey" PRIMARY KEY (id)'],
    )


async def test_constraint_drop_primary_key(gen_setup: GenerateSetup) -> None:
    """
    Primary key present in source but missing in target -> DROP CONSTRAINT.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (id integer NOT NULL)",
            "ALTER TABLE person ADD CONSTRAINT person_pkey PRIMARY KEY (id)",
        ],
        dst=["CREATE TABLE person (id integer NOT NULL)"],
        diff=['ALTER TABLE "public"."person" DROP CONSTRAINT "person_pkey"'],
    )


async def test_constraint_add_unique(gen_setup: GenerateSetup) -> None:
    """
    Unique constraint present in target but missing in source -> ADD CONSTRAINT.
    """
    await gen_setup.assert_diff(
        both=["CREATE TABLE person (email text)"],
        src=[],
        dst=["ALTER TABLE person ADD CONSTRAINT person_email_key UNIQUE (email)"],
        diff=['ALTER TABLE "public"."person" ADD CONSTRAINT "person_email_key" UNIQUE (email)'],
    )


async def test_constraint_drop_unique(gen_setup: GenerateSetup) -> None:
    """
    Unique constraint present in source but missing in target -> DROP CONSTRAINT.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (email text)",
            "ALTER TABLE person ADD CONSTRAINT person_email_key UNIQUE (email)",
        ],
        dst=["CREATE TABLE person (email text)"],
        diff=['ALTER TABLE "public"."person" DROP CONSTRAINT "person_email_key"'],
    )


async def test_constraint_rename(gen_setup: GenerateSetup) -> None:
    """
    Same definition on both sides, only the name differs -> RENAME CONSTRAINT.
    """
    await gen_setup.assert_diff(
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


async def test_constraint_rename_clears_comment(gen_setup: GenerateSetup) -> None:
    """
    A constraint renamed (same definition) whose source carries a comment but whose target
    does not: RENAME preserves the comment, so COMMENT ... IS NULL must also be emitted, else
    the migration does not converge.
    """
    await gen_setup.assert_diff(
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


async def test_constraint_definition_changed(gen_setup: GenerateSetup) -> None:
    """
    Same name, different definition -> DROP CONSTRAINT then ADD CONSTRAINT.
    """
    await gen_setup.assert_diff(
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


async def test_constraint_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Same name and definition on both sides -> no migration SQL.
    """
    await gen_setup.assert_diff(
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


async def test_constraint_primary_key_suppresses_set_not_null(gen_setup: GenerateSetup) -> None:
    """
    Adding a primary key on a source-nullable column emits only ADD CONSTRAINT;
    the redundant SET NOT NULL is suppressed.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (id integer)"],
        dst=[
            "CREATE TABLE person (id integer NOT NULL)",
            "ALTER TABLE person ADD CONSTRAINT person_pkey PRIMARY KEY (id)",
        ],
        diff=['ALTER TABLE "public"."person" ADD CONSTRAINT "person_pkey" PRIMARY KEY (id)'],
    )


async def test_constraint_dropped_with_table(gen_setup: GenerateSetup) -> None:
    """
    Table (with a constraint) dropped -> DROP TABLE only; the constraint rides along.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (id integer NOT NULL)",
            "ALTER TABLE person ADD CONSTRAINT person_pkey PRIMARY KEY (id)",
        ],
        dst=[],
        diff=['DROP TABLE "public"."person"'],
    )


async def test_constraint_add_check(gen_setup: GenerateSetup) -> None:
    """
    Check constraint present in target but missing in source -> ADD CONSTRAINT.
    """
    await gen_setup.assert_diff(
        src=["CREATE TABLE person (age integer)"],
        dst=[
            "CREATE TABLE person (age integer)",
            "ALTER TABLE person ADD CONSTRAINT person_age_check CHECK (age > 0)",
        ],
        diff=['ALTER TABLE "public"."person" ADD CONSTRAINT "person_age_check" CHECK ((age > 0))'],
    )


async def test_constraint_drop_check(gen_setup: GenerateSetup) -> None:
    """
    Check constraint present in source but missing in target -> DROP CONSTRAINT.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE person (age integer)",
            "ALTER TABLE person ADD CONSTRAINT person_age_check CHECK (age > 0)",
        ],
        dst=["CREATE TABLE person (age integer)"],
        diff=['ALTER TABLE "public"."person" DROP CONSTRAINT "person_age_check"'],
    )


async def test_constraint_rename_check(gen_setup: GenerateSetup) -> None:
    """
    Same check definition on both sides, only the name differs -> RENAME CONSTRAINT.
    """
    await gen_setup.assert_diff(
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


async def test_constraint_check_definition_changed(gen_setup: GenerateSetup) -> None:
    """
    Same name, different check expression -> DROP CONSTRAINT then ADD CONSTRAINT.
    """
    await gen_setup.assert_diff(
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


async def test_constraint_check_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Same check name and definition on both sides -> no migration SQL.
    """
    await gen_setup.assert_diff(
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


async def test_constraint_comment_added(gen_setup: GenerateSetup) -> None:
    """
    Comment added to a constraint present on both sides -> COMMENT ON CONSTRAINT.
    """
    await gen_setup.assert_diff(
        both=[
            "CREATE TABLE person (email text)",
            "ALTER TABLE person ADD CONSTRAINT person_email_key UNIQUE (email)",
        ],
        src=[],
        dst=["COMMENT ON CONSTRAINT person_email_key ON person IS 'unique email'"],
        diff=['COMMENT ON CONSTRAINT "person_email_key" ON "public"."person" IS \'unique email\''],
    )


async def test_foreign_key_comment_added(gen_setup: GenerateSetup) -> None:
    """
    Comment added to a foreign key -> COMMENT ON CONSTRAINT.
    """
    await gen_setup.assert_diff(
        both=[
            "CREATE TABLE team (id integer NOT NULL, CONSTRAINT team_pkey PRIMARY KEY (id))",
            "CREATE TABLE person (team_id integer)",
            "ALTER TABLE person ADD CONSTRAINT person_team_fkey FOREIGN KEY (team_id) REFERENCES team (id)",
        ],
        src=[],
        dst=["COMMENT ON CONSTRAINT person_team_fkey ON person IS 'team ref'"],
        diff=['COMMENT ON CONSTRAINT "person_team_fkey" ON "public"."person" IS \'team ref\''],
    )


async def test_constraint_add_exclusion(gen_setup: GenerateSetup) -> None:
    """
    Exclusion constraint (contype 'x') present in target but missing in source -> ADD CONSTRAINT.
    The backing gist index rides along with the constraint and is not emitted separately.
    """
    await gen_setup.assert_diff(
        both=["CREATE TABLE room (during int4range)"],
        src=[],
        dst=["ALTER TABLE room ADD CONSTRAINT room_during_excl EXCLUDE USING gist (during WITH &&)"],
        diff=['ALTER TABLE "public"."room" ADD CONSTRAINT "room_during_excl" EXCLUDE USING gist (during WITH &&)'],
    )


async def test_constraint_drop_exclusion(gen_setup: GenerateSetup) -> None:
    """
    Exclusion constraint present in source but missing in target -> DROP CONSTRAINT.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE room (during int4range)",
            "ALTER TABLE room ADD CONSTRAINT room_during_excl EXCLUDE USING gist (during WITH &&)",
        ],
        dst=["CREATE TABLE room (during int4range)"],
        diff=['ALTER TABLE "public"."room" DROP CONSTRAINT "room_during_excl"'],
    )


async def test_constraint_rename_exclusion(gen_setup: GenerateSetup) -> None:
    """
    Same exclusion definition on both sides, only the name differs -> RENAME CONSTRAINT.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE room (during int4range)",
            "ALTER TABLE room ADD CONSTRAINT room_excl_old EXCLUDE USING gist (during WITH &&)",
        ],
        dst=[
            "CREATE TABLE room (during int4range)",
            "ALTER TABLE room ADD CONSTRAINT room_excl_new EXCLUDE USING gist (during WITH &&)",
        ],
        diff=['ALTER TABLE "public"."room" RENAME CONSTRAINT "room_excl_old" TO "room_excl_new"'],
    )


async def test_constraint_exclusion_definition_changed(gen_setup: GenerateSetup) -> None:
    """
    Same name, different exclusion operator -> DROP CONSTRAINT then ADD CONSTRAINT.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE room (during int4range)",
            "ALTER TABLE room ADD CONSTRAINT room_excl EXCLUDE USING gist (during WITH &&)",
        ],
        dst=[
            "CREATE TABLE room (during int4range)",
            "ALTER TABLE room ADD CONSTRAINT room_excl EXCLUDE USING gist (during WITH -|-)",
        ],
        diff=[
            'ALTER TABLE "public"."room" DROP CONSTRAINT "room_excl"',
            'ALTER TABLE "public"."room" ADD CONSTRAINT "room_excl" EXCLUDE USING gist (during WITH -|-)',
        ],
    )


async def test_constraint_exclusion_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Same exclusion name and definition on both sides -> no migration SQL.
    """
    await gen_setup.assert_diff(
        src=[
            "CREATE TABLE room (during int4range)",
            "ALTER TABLE room ADD CONSTRAINT room_during_excl EXCLUDE USING gist (during WITH &&)",
        ],
        dst=[
            "CREATE TABLE room (during int4range)",
            "ALTER TABLE room ADD CONSTRAINT room_during_excl EXCLUDE USING gist (during WITH &&)",
        ],
        diff=[],
    )
