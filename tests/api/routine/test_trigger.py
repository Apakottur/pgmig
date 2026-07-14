from tests.api.generate_setup import GenerateSetup

# The trigger and its target table, both created on either side so tests isolate the trigger.
_TRIGGER = "CREATE TRIGGER person_audit AFTER INSERT ON person FOR EACH ROW EXECUTE FUNCTION log_change()"


def _setup_cmds() -> list[str]:
    """
    The trigger function and the table, run on both sides so tests isolate the trigger.
    """
    return [
        "CREATE FUNCTION log_change() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RETURN NEW; END;$$",
        "CREATE TABLE person (name text)",
    ]


def test_trigger_create(gen_setup: GenerateSetup) -> None:
    """
    Trigger present in target but missing in source -> CREATE TRIGGER.
    """
    gen_setup.assert_diff(
        both=_setup_cmds(),
        src=[],
        dst=[_TRIGGER],
        diff=[
            "CREATE TRIGGER person_audit AFTER INSERT ON public.person "
            "FOR EACH ROW EXECUTE FUNCTION public.log_change()"
        ],
    )


def test_trigger_drop(gen_setup: GenerateSetup) -> None:
    """
    Trigger present in source but missing in target -> DROP TRIGGER.
    """
    gen_setup.assert_diff(
        both=_setup_cmds(),
        src=[_TRIGGER],
        dst=[],
        diff=['DROP TRIGGER "person_audit" ON "public"."person"'],
    )


def test_trigger_rename(gen_setup: GenerateSetup) -> None:
    """
    Same definition on both sides, only the name differs -> ALTER TRIGGER RENAME.
    """
    gen_setup.assert_diff(
        both=_setup_cmds(),
        src=["CREATE TRIGGER audit_old AFTER INSERT ON person FOR EACH ROW EXECUTE FUNCTION log_change()"],
        dst=["CREATE TRIGGER audit_new AFTER INSERT ON person FOR EACH ROW EXECUTE FUNCTION log_change()"],
        diff=['ALTER TRIGGER "audit_old" ON "public"."person" RENAME TO "audit_new"'],
    )


def test_trigger_rename_clears_comment(gen_setup: GenerateSetup) -> None:
    """
    A trigger renamed (same definition) whose source carries a comment but whose target does
    not: RENAME preserves the comment, so COMMENT ... IS NULL must also be emitted, else the
    migration does not converge.
    """
    gen_setup.assert_diff(
        both=_setup_cmds(),
        src=[
            "CREATE TRIGGER audit_old AFTER INSERT ON person FOR EACH ROW EXECUTE FUNCTION log_change()",
            "COMMENT ON TRIGGER audit_old ON person IS 'audit'",
        ],
        dst=["CREATE TRIGGER audit_new AFTER INSERT ON person FOR EACH ROW EXECUTE FUNCTION log_change()"],
        diff=[
            'ALTER TRIGGER "audit_old" ON "public"."person" RENAME TO "audit_new"',
            'COMMENT ON TRIGGER "audit_new" ON "public"."person" IS NULL',
        ],
    )


def test_trigger_definition_changed(gen_setup: GenerateSetup) -> None:
    """
    Same name, different definition -> DROP TRIGGER then CREATE TRIGGER.
    """
    gen_setup.assert_diff(
        both=_setup_cmds(),
        src=[_TRIGGER],
        dst=["CREATE TRIGGER person_audit AFTER UPDATE ON person FOR EACH ROW EXECUTE FUNCTION log_change()"],
        diff=[
            'DROP TRIGGER "person_audit" ON "public"."person"',
            "CREATE TRIGGER person_audit AFTER UPDATE ON public.person "
            "FOR EACH ROW EXECUTE FUNCTION public.log_change()",
        ],
    )


def test_trigger_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical trigger on both sides -> no migration SQL.
    """
    gen_setup.assert_diff(
        both=[*_setup_cmds(), _TRIGGER],
        src=[],
        dst=[],
        diff=[],
    )


def test_trigger_internal_ignored(gen_setup: GenerateSetup) -> None:
    """
    A foreign key's internal RI trigger is not diffed as a user trigger.
    """
    gen_setup.assert_diff(
        both=[
            "CREATE TABLE team (id integer NOT NULL, CONSTRAINT team_pkey PRIMARY KEY (id))",
            "CREATE TABLE person (team_id integer)",
            "ALTER TABLE person ADD CONSTRAINT person_team_fkey FOREIGN KEY (team_id) REFERENCES team (id)",
        ],
        src=[],
        dst=[],
        diff=[],
    )


def test_trigger_comment_added(gen_setup: GenerateSetup) -> None:
    """
    Identical trigger both sides, comment only on target -> COMMENT ON TRIGGER.
    """
    gen_setup.assert_diff(
        both=[*_setup_cmds(), _TRIGGER],
        src=[],
        dst=["COMMENT ON TRIGGER person_audit ON person IS 'audit'"],
        diff=['COMMENT ON TRIGGER "person_audit" ON "public"."person" IS \'audit\''],
    )


def test_trigger_comment_changed(gen_setup: GenerateSetup) -> None:
    """
    Same trigger both sides with differing comments -> COMMENT ON TRIGGER with target's.
    """
    gen_setup.assert_diff(
        both=[*_setup_cmds(), _TRIGGER],
        src=["COMMENT ON TRIGGER person_audit ON person IS 'old'"],
        dst=["COMMENT ON TRIGGER person_audit ON person IS 'new'"],
        diff=['COMMENT ON TRIGGER "person_audit" ON "public"."person" IS \'new\''],
    )


def test_trigger_comment_removed(gen_setup: GenerateSetup) -> None:
    """
    Comment on source trigger but none on target -> COMMENT ON TRIGGER ... IS NULL.
    """
    gen_setup.assert_diff(
        both=[*_setup_cmds(), _TRIGGER],
        src=["COMMENT ON TRIGGER person_audit ON person IS 'audit'"],
        dst=[],
        diff=['COMMENT ON TRIGGER "person_audit" ON "public"."person" IS NULL'],
    )


def _partition_setup_cmds() -> list[str]:
    """
    The trigger function plus a range-partitioned parent and one partition, on both sides.
    """
    return [
        "CREATE FUNCTION log_change() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RETURN NEW; END;$$",
        "CREATE TABLE events (id integer NOT NULL) PARTITION BY RANGE (id)",
        "CREATE TABLE events_2024 PARTITION OF events FOR VALUES FROM (1) TO (100)",
    ]


def test_trigger_on_partitioned_parent_create(gen_setup: GenerateSetup) -> None:
    """
    A trigger declared on a partitioned parent is emitted once against the parent, not
    once per partition clone: Postgres cascades the parent declaration to every partition.
    """
    gen_setup.assert_diff(
        both=_partition_setup_cmds(),
        src=[],
        dst=["CREATE TRIGGER events_audit AFTER INSERT ON events FOR EACH ROW EXECUTE FUNCTION log_change()"],
        diff=[
            "CREATE TRIGGER events_audit AFTER INSERT ON public.events "
            "FOR EACH ROW EXECUTE FUNCTION public.log_change()"
        ],
    )


def test_trigger_on_partitioned_parent_drop(gen_setup: GenerateSetup) -> None:
    """
    Dropping a partitioned parent's trigger emits a single DROP against the parent. The
    per-partition clones must not be diffed: Postgres refuses to drop them directly.
    """
    gen_setup.assert_diff(
        both=_partition_setup_cmds(),
        src=["CREATE TRIGGER events_audit AFTER INSERT ON events FOR EACH ROW EXECUTE FUNCTION log_change()"],
        dst=[],
        diff=['DROP TRIGGER "events_audit" ON "public"."events"'],
    )


def test_trigger_comment_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Same trigger and same comment on both sides -> no migration SQL.
    """
    gen_setup.assert_diff(
        both=[*_setup_cmds(), _TRIGGER, "COMMENT ON TRIGGER person_audit ON person IS 'audit'"],
        src=[],
        dst=[],
        diff=[],
    )
