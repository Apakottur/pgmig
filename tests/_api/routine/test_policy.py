from tests._api.generate_setup import GenerateSetup

# The table policies attach to, created on both sides so tests isolate the policy.
_TABLE = "CREATE TABLE person (id integer, team text)"


async def test_policy_create(gen_setup: GenerateSetup) -> None:
    """
    Policy present in target but missing in source -> CREATE POLICY.
    """
    await gen_setup.assert_diff(
        both=[_TABLE],
        src=[],
        dst=["CREATE POLICY person_sel ON person USING (true)"],
        diff=['CREATE POLICY "person_sel" ON "public"."person" USING (true)'],
    )


async def test_policy_drop(gen_setup: GenerateSetup) -> None:
    """
    Policy present in source but missing in target -> DROP POLICY.
    """
    await gen_setup.assert_diff(
        both=[_TABLE],
        src=["CREATE POLICY person_sel ON person USING (true)"],
        dst=[],
        diff=['DROP POLICY "person_sel" ON "public"."person"'],
    )


async def test_policy_definition_changed(gen_setup: GenerateSetup) -> None:
    """
    Same name, different USING expression -> DROP POLICY then CREATE POLICY (no ALTER form).
    """
    await gen_setup.assert_diff(
        both=[_TABLE],
        src=["CREATE POLICY person_sel ON person USING (id > 0)"],
        dst=["CREATE POLICY person_sel ON person USING (id > 5)"],
        diff=[
            'DROP POLICY "person_sel" ON "public"."person"',
            'CREATE POLICY "person_sel" ON "public"."person" USING ((id > 5))',
        ],
    )


async def test_policy_unchanged(gen_setup: GenerateSetup) -> None:
    """
    Identical policy on both sides -> no migration SQL.
    """
    await gen_setup.assert_diff(
        both=[_TABLE, "CREATE POLICY person_sel ON person USING (true)"],
        src=[],
        dst=[],
        diff=[],
    )


async def test_policy_restrictive(gen_setup: GenerateSetup) -> None:
    """
    A RESTRICTIVE policy renders the AS RESTRICTIVE clause (PERMISSIVE is the default, omitted).
    """
    await gen_setup.assert_diff(
        both=[_TABLE],
        src=[],
        dst=["CREATE POLICY person_sel ON person AS RESTRICTIVE USING (true)"],
        diff=['CREATE POLICY "person_sel" ON "public"."person" AS RESTRICTIVE USING (true)'],
    )


async def test_policy_for_command(gen_setup: GenerateSetup) -> None:
    """
    A policy scoped to one command renders FOR <cmd> (FOR ALL is the default, omitted).
    """
    await gen_setup.assert_diff(
        both=[_TABLE],
        src=[],
        dst=["CREATE POLICY person_sel ON person FOR SELECT USING (true)"],
        diff=['CREATE POLICY "person_sel" ON "public"."person" FOR SELECT USING (true)'],
    )


async def test_policy_to_role(gen_setup: GenerateSetup) -> None:
    """
    A policy naming a role renders the TO clause (TO PUBLIC is the default, omitted). Uses the
    predefined pg_read_all_data role so no CREATE ROLE (roles are not modelled) is needed.
    """
    await gen_setup.assert_diff(
        both=[_TABLE],
        src=[],
        dst=["CREATE POLICY person_sel ON person TO pg_read_all_data USING (true)"],
        diff=['CREATE POLICY "person_sel" ON "public"."person" TO "pg_read_all_data" USING (true)'],
    )


async def test_policy_with_check(gen_setup: GenerateSetup) -> None:
    """
    An INSERT policy carries WITH CHECK (and no USING).
    """
    await gen_setup.assert_diff(
        both=[_TABLE],
        src=[],
        dst=["CREATE POLICY person_ins ON person FOR INSERT WITH CHECK (id > 0)"],
        diff=['CREATE POLICY "person_ins" ON "public"."person" FOR INSERT WITH CHECK ((id > 0))'],
    )


async def test_policy_comment_added(gen_setup: GenerateSetup) -> None:
    """
    Identical policy both sides, comment only on target -> COMMENT ON POLICY.
    """
    await gen_setup.assert_diff(
        both=[_TABLE, "CREATE POLICY person_sel ON person USING (true)"],
        src=[],
        dst=["COMMENT ON POLICY person_sel ON person IS 'audit'"],
        diff=['COMMENT ON POLICY "person_sel" ON "public"."person" IS \'audit\''],
    )


async def test_policy_comment_removed(gen_setup: GenerateSetup) -> None:
    """
    Comment on source policy but none on target -> COMMENT ON POLICY ... IS NULL.
    """
    await gen_setup.assert_diff(
        both=[_TABLE, "CREATE POLICY person_sel ON person USING (true)"],
        src=["COMMENT ON POLICY person_sel ON person IS 'audit'"],
        dst=[],
        diff=['COMMENT ON POLICY "person_sel" ON "public"."person" IS NULL'],
    )
