from tests._api.generate_setup import GenerateSetup

# An INSTEAD OF trigger and its target view, both created on either side so tests isolate the
# trigger. INSTEAD OF triggers are only legal on views (relkind 'v').
_TRIGGER = "CREATE TRIGGER person_v_ins INSTEAD OF INSERT ON person_v FOR EACH ROW EXECUTE FUNCTION v_change()"


def _setup_cmds() -> list[str]:
    """
    The trigger function and the view, run on both sides so tests isolate the trigger.
    """
    return [
        "CREATE FUNCTION v_change() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RETURN NEW; END;$$",
        "CREATE VIEW person_v AS SELECT 1 AS id",
    ]


async def test_view_trigger_create(gen_setup: GenerateSetup) -> None:
    """
    INSTEAD OF trigger present in target but missing in source -> CREATE TRIGGER on the view.
    """
    await gen_setup.assert_diff(
        both=_setup_cmds(),
        src=[],
        dst=[_TRIGGER],
        diff=[
            "CREATE TRIGGER person_v_ins INSTEAD OF INSERT ON public.person_v "
            "FOR EACH ROW EXECUTE FUNCTION public.v_change()"
        ],
    )


async def test_view_trigger_drop(gen_setup: GenerateSetup) -> None:
    """
    INSTEAD OF trigger present in source but missing in target -> DROP TRIGGER on the view.
    """
    await gen_setup.assert_diff(
        both=_setup_cmds(),
        src=[_TRIGGER],
        dst=[],
        diff=['DROP TRIGGER "person_v_ins" ON "public"."person_v"'],
    )


async def test_view_trigger_rename(gen_setup: GenerateSetup) -> None:
    """
    Same definition on both sides, only the name differs -> ALTER TRIGGER RENAME.
    """
    await gen_setup.assert_diff(
        both=_setup_cmds(),
        src=["CREATE TRIGGER ins_old INSTEAD OF INSERT ON person_v FOR EACH ROW EXECUTE FUNCTION v_change()"],
        dst=["CREATE TRIGGER ins_new INSTEAD OF INSERT ON person_v FOR EACH ROW EXECUTE FUNCTION v_change()"],
        diff=['ALTER TRIGGER "ins_old" ON "public"."person_v" RENAME TO "ins_new"'],
    )


async def test_view_trigger_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical INSTEAD OF trigger on both sides -> no migration SQL.
    """
    await gen_setup.assert_diff(
        both=[*_setup_cmds(), _TRIGGER],
        src=[],
        dst=[],
        diff=[],
    )


async def test_view_trigger_definition_changed(gen_setup: GenerateSetup) -> None:
    """
    Same name, different definition (INSERT -> UPDATE) -> DROP TRIGGER then CREATE TRIGGER,
    both against the (unchanged) view.
    """
    await gen_setup.assert_diff(
        both=_setup_cmds(),
        src=[_TRIGGER],
        dst=["CREATE TRIGGER person_v_ins INSTEAD OF UPDATE ON person_v FOR EACH ROW EXECUTE FUNCTION v_change()"],
        diff=[
            'DROP TRIGGER "person_v_ins" ON "public"."person_v"',
            "CREATE TRIGGER person_v_ins INSTEAD OF UPDATE ON public.person_v "
            "FOR EACH ROW EXECUTE FUNCTION public.v_change()",
        ],
    )


async def test_view_trigger_survives_view_recreate(gen_setup: GenerateSetup) -> None:
    """
    Key ordering constraint: a changed view definition is a DROP VIEW + CREATE VIEW, which
    silently destroys the view's triggers. The trigger diff must re-emit every target trigger
    after VIEW_CREATE (and emit no DROP TRIGGER against the already-dropped view), exactly as a
    recreated table would. The trigger is identical on both sides, so a naive diff would emit
    nothing -- and the recreated view would lose it.
    """
    await gen_setup.assert_diff(
        both=["CREATE FUNCTION v_change() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RETURN NEW; END;$$"],
        src=["CREATE VIEW person_v AS SELECT 1 AS id", _TRIGGER],
        dst=["CREATE VIEW person_v AS SELECT 2 AS id", _TRIGGER],
        diff=[
            'DROP VIEW "public"."person_v"',
            'CREATE VIEW "public"."person_v" AS SELECT 2 AS id',
            "CREATE TRIGGER person_v_ins INSTEAD OF INSERT ON public.person_v "
            "FOR EACH ROW EXECUTE FUNCTION public.v_change()",
        ],
    )


async def test_view_trigger_comment_added(gen_setup: GenerateSetup) -> None:
    """
    Identical trigger both sides, comment only on target -> COMMENT ON TRIGGER.
    """
    await gen_setup.assert_diff(
        both=[*_setup_cmds(), _TRIGGER],
        src=[],
        dst=["COMMENT ON TRIGGER person_v_ins ON person_v IS 'audit'"],
        diff=['COMMENT ON TRIGGER "person_v_ins" ON "public"."person_v" IS \'audit\''],
    )
