from tests.fixtures.generate_setup import GenerateSetup

_FUNCTION = "CREATE FUNCTION log_change() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RETURN NEW; END;$$"


def _setup(gen_setup: GenerateSetup) -> None:
    """
    Create the trigger function and the table on both sides, so tests isolate the trigger.
    """
    gen_setup.execute_both(_FUNCTION)
    gen_setup.execute_both("CREATE TABLE person (name text)")


def test_trigger_create(gen_setup: GenerateSetup) -> None:
    """
    Trigger present in target but missing in source -> CREATE TRIGGER.
    """
    _setup(gen_setup)
    gen_setup.dst.execute(
        "CREATE TRIGGER person_audit AFTER INSERT ON person FOR EACH ROW EXECUTE FUNCTION log_change()"
    )

    gen_setup.assert_migration_sql(
        "CREATE TRIGGER person_audit AFTER INSERT ON public.person FOR EACH ROW EXECUTE FUNCTION log_change();"
    )


def test_trigger_drop(gen_setup: GenerateSetup) -> None:
    """
    Trigger present in source but missing in target -> DROP TRIGGER.
    """
    _setup(gen_setup)
    gen_setup.src.execute(
        "CREATE TRIGGER person_audit AFTER INSERT ON person FOR EACH ROW EXECUTE FUNCTION log_change()"
    )

    gen_setup.assert_migration_sql('DROP TRIGGER "person_audit" ON "public"."person";')


def test_trigger_rename(gen_setup: GenerateSetup) -> None:
    """
    Same definition on both sides, only the name differs -> ALTER TRIGGER RENAME.
    """
    _setup(gen_setup)
    gen_setup.src.execute("CREATE TRIGGER audit_old AFTER INSERT ON person FOR EACH ROW EXECUTE FUNCTION log_change()")
    gen_setup.dst.execute("CREATE TRIGGER audit_new AFTER INSERT ON person FOR EACH ROW EXECUTE FUNCTION log_change()")

    gen_setup.assert_migration_sql('ALTER TRIGGER "audit_old" ON "public"."person" RENAME TO "audit_new";')


def test_trigger_definition_changed(gen_setup: GenerateSetup) -> None:
    """
    Same name, different definition -> DROP TRIGGER then CREATE TRIGGER.
    """
    _setup(gen_setup)
    gen_setup.src.execute(
        "CREATE TRIGGER person_audit AFTER INSERT ON person FOR EACH ROW EXECUTE FUNCTION log_change()"
    )
    gen_setup.dst.execute(
        "CREATE TRIGGER person_audit AFTER UPDATE ON person FOR EACH ROW EXECUTE FUNCTION log_change()"
    )

    gen_setup.assert_migration_sql(
        [
            'DROP TRIGGER "person_audit" ON "public"."person";',
            "CREATE TRIGGER person_audit AFTER UPDATE ON public.person FOR EACH ROW EXECUTE FUNCTION log_change();",
        ]
    )


def test_trigger_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical trigger on both sides -> no migration SQL.
    """
    _setup(gen_setup)
    gen_setup.execute_both(
        "CREATE TRIGGER person_audit AFTER INSERT ON person FOR EACH ROW EXECUTE FUNCTION log_change()"
    )

    gen_setup.assert_migration_sql("")


def test_trigger_internal_ignored(gen_setup: GenerateSetup) -> None:
    """
    A foreign key's internal RI trigger is not diffed as a user trigger.
    """
    gen_setup.execute_both("CREATE TABLE team (id integer NOT NULL, CONSTRAINT team_pkey PRIMARY KEY (id))")
    gen_setup.execute_both("CREATE TABLE person (team_id integer)")
    gen_setup.execute_both(
        "ALTER TABLE person ADD CONSTRAINT person_team_fkey FOREIGN KEY (team_id) REFERENCES team (id)"
    )

    gen_setup.assert_migration_sql("")
