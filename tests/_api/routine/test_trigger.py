from tests._api.generate_setup import GenerateSetup

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


async def test_trigger_create(gen_setup: GenerateSetup) -> None:
    """
    Trigger present in target but missing in source -> CREATE TRIGGER.
    """
    await gen_setup.assert_diff(
        both=_setup_cmds(),
        src=[],
        dst=[_TRIGGER],
        diff=[
            "CREATE TRIGGER person_audit AFTER INSERT ON public.person "
            "FOR EACH ROW EXECUTE FUNCTION public.log_change()"
        ],
    )


async def test_trigger_drop(gen_setup: GenerateSetup) -> None:
    """
    Trigger present in source but missing in target -> DROP TRIGGER.
    """
    await gen_setup.assert_diff(
        both=_setup_cmds(),
        src=[_TRIGGER],
        dst=[],
        diff=['DROP TRIGGER "person_audit" ON "public"."person"'],
    )


async def test_trigger_rename(gen_setup: GenerateSetup) -> None:
    """
    Same definition on both sides, only the name differs -> ALTER TRIGGER RENAME.
    """
    await gen_setup.assert_diff(
        both=_setup_cmds(),
        src=["CREATE TRIGGER audit_old AFTER INSERT ON person FOR EACH ROW EXECUTE FUNCTION log_change()"],
        dst=["CREATE TRIGGER audit_new AFTER INSERT ON person FOR EACH ROW EXECUTE FUNCTION log_change()"],
        diff=['ALTER TRIGGER "audit_old" ON "public"."person" RENAME TO "audit_new"'],
    )


async def test_trigger_rename_clears_comment(gen_setup: GenerateSetup) -> None:
    """
    A trigger renamed (same definition) whose source carries a comment but whose target does
    not: RENAME preserves the comment, so COMMENT ... IS NULL must also be emitted, else the
    migration does not converge.
    """
    await gen_setup.assert_diff(
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


async def test_trigger_definition_changed(gen_setup: GenerateSetup) -> None:
    """
    Same name, different definition -> DROP TRIGGER then CREATE TRIGGER.
    """
    await gen_setup.assert_diff(
        both=_setup_cmds(),
        src=[_TRIGGER],
        dst=["CREATE TRIGGER person_audit AFTER UPDATE ON person FOR EACH ROW EXECUTE FUNCTION log_change()"],
        diff=[
            'DROP TRIGGER "person_audit" ON "public"."person"',
            "CREATE TRIGGER person_audit AFTER UPDATE ON public.person "
            "FOR EACH ROW EXECUTE FUNCTION public.log_change()",
        ],
    )


async def test_trigger_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical trigger on both sides -> no migration SQL.
    """
    await gen_setup.assert_diff(
        both=[*_setup_cmds(), _TRIGGER],
        src=[],
        dst=[],
        diff=[],
    )


async def test_trigger_internal_ignored(gen_setup: GenerateSetup) -> None:
    """
    A foreign key's internal RI trigger is not diffed as a user trigger.
    """
    await gen_setup.assert_diff(
        both=[
            "CREATE TABLE team (id integer NOT NULL, CONSTRAINT team_pkey PRIMARY KEY (id))",
            "CREATE TABLE person (team_id integer)",
            "ALTER TABLE person ADD CONSTRAINT person_team_fkey FOREIGN KEY (team_id) REFERENCES team (id)",
        ],
        src=[],
        dst=[],
        diff=[],
    )


async def test_trigger_comment_added(gen_setup: GenerateSetup) -> None:
    """
    Identical trigger both sides, comment only on target -> COMMENT ON TRIGGER.
    """
    await gen_setup.assert_diff(
        both=[*_setup_cmds(), _TRIGGER],
        src=[],
        dst=["COMMENT ON TRIGGER person_audit ON person IS 'audit'"],
        diff=['COMMENT ON TRIGGER "person_audit" ON "public"."person" IS \'audit\''],
    )


async def test_trigger_comment_changed(gen_setup: GenerateSetup) -> None:
    """
    Same trigger both sides with differing comments -> COMMENT ON TRIGGER with target's.
    """
    await gen_setup.assert_diff(
        both=[*_setup_cmds(), _TRIGGER],
        src=["COMMENT ON TRIGGER person_audit ON person IS 'old'"],
        dst=["COMMENT ON TRIGGER person_audit ON person IS 'new'"],
        diff=['COMMENT ON TRIGGER "person_audit" ON "public"."person" IS \'new\''],
    )


async def test_trigger_comment_removed(gen_setup: GenerateSetup) -> None:
    """
    Comment on source trigger but none on target -> COMMENT ON TRIGGER ... IS NULL.
    """
    await gen_setup.assert_diff(
        both=[*_setup_cmds(), _TRIGGER],
        src=["COMMENT ON TRIGGER person_audit ON person IS 'audit'"],
        dst=[],
        diff=['COMMENT ON TRIGGER "person_audit" ON "public"."person" IS NULL'],
    )


async def test_trigger_disabled(gen_setup: GenerateSetup) -> None:
    """
    Same trigger both sides, disabled only on target -> ALTER TABLE ... DISABLE TRIGGER.
    pg_get_triggerdef omits the enable state, so this is caught only via tgenabled.
    """
    await gen_setup.assert_diff(
        both=[*_setup_cmds(), _TRIGGER],
        src=[],
        dst=["ALTER TABLE person DISABLE TRIGGER person_audit"],
        diff=['ALTER TABLE "public"."person" DISABLE TRIGGER "person_audit"'],
    )


async def test_trigger_reenabled(gen_setup: GenerateSetup) -> None:
    """
    Disabled on source, back to default (enabled) on target -> ALTER TABLE ... ENABLE TRIGGER.
    """
    await gen_setup.assert_diff(
        both=[*_setup_cmds(), _TRIGGER],
        src=["ALTER TABLE person DISABLE TRIGGER person_audit"],
        dst=[],
        diff=['ALTER TABLE "public"."person" ENABLE TRIGGER "person_audit"'],
    )


async def test_trigger_enable_replica(gen_setup: GenerateSetup) -> None:
    """
    Default on source, ENABLE REPLICA on target -> ALTER TABLE ... ENABLE REPLICA TRIGGER.
    """
    await gen_setup.assert_diff(
        both=[*_setup_cmds(), _TRIGGER],
        src=[],
        dst=["ALTER TABLE person ENABLE REPLICA TRIGGER person_audit"],
        diff=['ALTER TABLE "public"."person" ENABLE REPLICA TRIGGER "person_audit"'],
    )


async def test_trigger_enable_always(gen_setup: GenerateSetup) -> None:
    """
    Default on source, ENABLE ALWAYS on target -> ALTER TABLE ... ENABLE ALWAYS TRIGGER.
    """
    await gen_setup.assert_diff(
        both=[*_setup_cmds(), _TRIGGER],
        src=[],
        dst=["ALTER TABLE person ENABLE ALWAYS TRIGGER person_audit"],
        diff=['ALTER TABLE "public"."person" ENABLE ALWAYS TRIGGER "person_audit"'],
    )


async def test_trigger_state_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Same trigger, same non-default (disabled) state on both sides -> no migration SQL.
    """
    await gen_setup.assert_diff(
        both=[
            *_setup_cmds(),
            _TRIGGER,
            "ALTER TABLE person DISABLE TRIGGER person_audit",
        ],
        src=[],
        dst=[],
        diff=[],
    )


async def test_trigger_create_disabled(gen_setup: GenerateSetup) -> None:
    """
    Trigger absent on source, present-and-disabled on target: CREATE TRIGGER yields the
    default (enabled) state, so a DISABLE must follow to reach the target state.
    """
    await gen_setup.assert_diff(
        both=_setup_cmds(),
        src=[],
        dst=[_TRIGGER, "ALTER TABLE person DISABLE TRIGGER person_audit"],
        diff=[
            "CREATE TRIGGER person_audit AFTER INSERT ON public.person "
            "FOR EACH ROW EXECUTE FUNCTION public.log_change()",
            'ALTER TABLE "public"."person" DISABLE TRIGGER "person_audit"',
        ],
    )


async def test_trigger_recreated_preserves_disabled_state(
    gen_setup: GenerateSetup,
) -> None:
    """
    Definition changed and target is disabled: the DROP/CREATE resets the trigger to the
    default enabled state, so a DISABLE must follow the recreate to converge.
    """
    await gen_setup.assert_diff(
        both=_setup_cmds(),
        src=[_TRIGGER],
        dst=[
            "CREATE TRIGGER person_audit AFTER UPDATE ON person FOR EACH ROW EXECUTE FUNCTION log_change()",
            "ALTER TABLE person DISABLE TRIGGER person_audit",
        ],
        diff=[
            'DROP TRIGGER "person_audit" ON "public"."person"',
            "CREATE TRIGGER person_audit AFTER UPDATE ON public.person "
            "FOR EACH ROW EXECUTE FUNCTION public.log_change()",
            'ALTER TABLE "public"."person" DISABLE TRIGGER "person_audit"',
        ],
    )


async def test_trigger_renamed_preserves_disabled_state(
    gen_setup: GenerateSetup,
) -> None:
    """
    A disabled trigger renamed (same definition, still disabled on both sides): RENAME
    preserves the enable state, so only the rename is emitted -- no redundant DISABLE.
    """
    await gen_setup.assert_diff(
        both=_setup_cmds(),
        src=[
            "CREATE TRIGGER audit_old AFTER INSERT ON person FOR EACH ROW EXECUTE FUNCTION log_change()",
            "ALTER TABLE person DISABLE TRIGGER audit_old",
        ],
        dst=[
            "CREATE TRIGGER audit_new AFTER INSERT ON person FOR EACH ROW EXECUTE FUNCTION log_change()",
            "ALTER TABLE person DISABLE TRIGGER audit_new",
        ],
        diff=['ALTER TRIGGER "audit_old" ON "public"."person" RENAME TO "audit_new"'],
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


async def test_trigger_on_partitioned_parent_create(gen_setup: GenerateSetup) -> None:
    """
    A trigger declared on a partitioned parent is emitted once against the parent, not
    once per partition clone: Postgres cascades the parent declaration to every partition.
    """
    await gen_setup.assert_diff(
        both=_partition_setup_cmds(),
        src=[],
        dst=["CREATE TRIGGER events_audit AFTER INSERT ON events FOR EACH ROW EXECUTE FUNCTION log_change()"],
        diff=[
            "CREATE TRIGGER events_audit AFTER INSERT ON public.events "
            "FOR EACH ROW EXECUTE FUNCTION public.log_change()"
        ],
    )


async def test_trigger_on_partitioned_parent_drop(gen_setup: GenerateSetup) -> None:
    """
    Dropping a partitioned parent's trigger emits a single DROP against the parent. The
    per-partition clones must not be diffed: Postgres refuses to drop them directly.
    """
    await gen_setup.assert_diff(
        both=_partition_setup_cmds(),
        src=["CREATE TRIGGER events_audit AFTER INSERT ON events FOR EACH ROW EXECUTE FUNCTION log_change()"],
        dst=[],
        diff=['DROP TRIGGER "events_audit" ON "public"."events"'],
    )


async def test_trigger_comment_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Same trigger and same comment on both sides -> no migration SQL.
    """
    await gen_setup.assert_diff(
        both=[
            *_setup_cmds(),
            _TRIGGER,
            "COMMENT ON TRIGGER person_audit ON person IS 'audit'",
        ],
        src=[],
        dst=[],
        diff=[],
    )


# Constraint triggers (CREATE CONSTRAINT TRIGGER) are ordinary user triggers (tgisinternal =
# false), so they flow through the same trigger diff path. pg_get_triggerdef spells them out
# in full, always emitting the deferral clause (NOT DEFERRABLE INITIALLY IMMEDIATE by default),
# and the canonical rename key strips the name from "CONSTRAINT TRIGGER <name> " just as it does
# from a plain "TRIGGER <name> ".
_CONSTRAINT_TRIGGER = (
    "CREATE CONSTRAINT TRIGGER person_check AFTER INSERT ON person FOR EACH ROW EXECUTE FUNCTION log_change()"
)
_CONSTRAINT_TRIGGER_DEF = (
    "CREATE CONSTRAINT TRIGGER person_check AFTER INSERT ON public.person "
    "NOT DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION public.log_change()"
)
_CONSTRAINT_TRIGGER_DEFERRED = (
    "CREATE CONSTRAINT TRIGGER person_check AFTER INSERT ON person "
    "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION log_change()"
)
_CONSTRAINT_TRIGGER_DEFERRED_DEF = (
    "CREATE CONSTRAINT TRIGGER person_check AFTER INSERT ON public.person "
    "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.log_change()"
)


async def test_constraint_trigger_create(gen_setup: GenerateSetup) -> None:
    """
    Constraint trigger present in target but missing in source -> CREATE CONSTRAINT TRIGGER.
    """
    await gen_setup.assert_diff(
        both=_setup_cmds(),
        src=[],
        dst=[_CONSTRAINT_TRIGGER],
        diff=[_CONSTRAINT_TRIGGER_DEF],
    )


async def test_constraint_trigger_drop(gen_setup: GenerateSetup) -> None:
    """
    Constraint trigger present in source but missing in target -> DROP TRIGGER (constraint
    triggers are dropped with plain DROP TRIGGER, same as ordinary triggers).
    """
    await gen_setup.assert_diff(
        both=_setup_cmds(),
        src=[_CONSTRAINT_TRIGGER],
        dst=[],
        diff=['DROP TRIGGER "person_check" ON "public"."person"'],
    )


async def test_constraint_trigger_rename(gen_setup: GenerateSetup) -> None:
    """
    Same constraint trigger definition on both sides, only the name differs -> ALTER TRIGGER
    RENAME. Proves the canonical key strips the name from "CONSTRAINT TRIGGER <name> ".
    """
    await gen_setup.assert_diff(
        both=_setup_cmds(),
        src=["CREATE CONSTRAINT TRIGGER check_old AFTER INSERT ON person FOR EACH ROW EXECUTE FUNCTION log_change()"],
        dst=["CREATE CONSTRAINT TRIGGER check_new AFTER INSERT ON person FOR EACH ROW EXECUTE FUNCTION log_change()"],
        diff=['ALTER TRIGGER "check_old" ON "public"."person" RENAME TO "check_new"'],
    )


async def test_constraint_trigger_definition_changed(gen_setup: GenerateSetup) -> None:
    """
    Same name, different constraint trigger definition -> DROP then CREATE (recreate).
    """
    await gen_setup.assert_diff(
        both=_setup_cmds(),
        src=[_CONSTRAINT_TRIGGER],
        dst=[
            "CREATE CONSTRAINT TRIGGER person_check AFTER UPDATE ON person FOR EACH ROW EXECUTE FUNCTION log_change()"
        ],
        diff=[
            'DROP TRIGGER "person_check" ON "public"."person"',
            "CREATE CONSTRAINT TRIGGER person_check AFTER UPDATE ON public.person "
            "NOT DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION public.log_change()",
        ],
    )


async def test_constraint_trigger_deferrable_create(gen_setup: GenerateSetup) -> None:
    """
    A DEFERRABLE INITIALLY DEFERRED constraint trigger round-trips its deferral clause verbatim.
    """
    await gen_setup.assert_diff(
        both=_setup_cmds(),
        src=[],
        dst=[_CONSTRAINT_TRIGGER_DEFERRED],
        diff=[_CONSTRAINT_TRIGGER_DEFERRED_DEF],
    )


async def test_constraint_trigger_deferrability_changed(gen_setup: GenerateSetup) -> None:
    """
    Only the deferral clause differs -> the canonical forms differ, so it is a recreate
    (DROP + CREATE), carrying the target's deferral clause.
    """
    await gen_setup.assert_diff(
        both=_setup_cmds(),
        src=[_CONSTRAINT_TRIGGER],
        dst=[_CONSTRAINT_TRIGGER_DEFERRED],
        diff=[
            'DROP TRIGGER "person_check" ON "public"."person"',
            _CONSTRAINT_TRIGGER_DEFERRED_DEF,
        ],
    )


async def test_constraint_trigger_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical constraint trigger on both sides -> no migration SQL.
    """
    await gen_setup.assert_diff(
        both=[*_setup_cmds(), _CONSTRAINT_TRIGGER],
        src=[],
        dst=[],
        diff=[],
    )
