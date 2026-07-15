from tests._api.generate_setup import GenerateSetup


def test_index_redefinition_reemits_identical_comment(gen_setup: GenerateSetup) -> None:
    """
    An index redefined on both sides but carrying the same comment must have its comment
    re-emitted: the drop-and-recreate resets it to NULL, so skipping COMMENT ON would
    leave a residual diff (convergence violation).
    """
    gen_setup.assert_diff(
        src=[
            "CREATE TABLE t (a integer, b integer)",
            "CREATE INDEX my_idx ON t (a)",
            "COMMENT ON INDEX my_idx IS 'hi'",
        ],
        dst=[
            "CREATE TABLE t (a integer, b integer)",
            "CREATE INDEX my_idx ON t (b)",
            "COMMENT ON INDEX my_idx IS 'hi'",
        ],
        diff=[
            'DROP INDEX "public"."my_idx"',
            "CREATE INDEX my_idx ON public.t USING btree (b)",
            'COMMENT ON INDEX "public"."my_idx" IS \'hi\'',
        ],
    )


def test_constraint_redefinition_reemits_identical_comment(gen_setup: GenerateSetup) -> None:
    """
    A check constraint redefined on both sides with the same comment must re-emit it;
    the drop-and-recreate resets it.
    """
    gen_setup.assert_diff(
        both=["CREATE TABLE t (a integer)"],
        src=[
            "ALTER TABLE t ADD CONSTRAINT c_pos CHECK (a > 0)",
            "COMMENT ON CONSTRAINT c_pos ON t IS 'hi'",
        ],
        dst=[
            "ALTER TABLE t ADD CONSTRAINT c_pos CHECK (a > 1)",
            "COMMENT ON CONSTRAINT c_pos ON t IS 'hi'",
        ],
        diff=[
            'ALTER TABLE "public"."t" DROP CONSTRAINT "c_pos"',
            'ALTER TABLE "public"."t" ADD CONSTRAINT "c_pos" CHECK ((a > 1))',
            'COMMENT ON CONSTRAINT "c_pos" ON "public"."t" IS \'hi\'',
        ],
    )


def test_function_return_type_change_reemits_identical_comment(gen_setup: GenerateSetup) -> None:
    """
    A routine whose return type changes is dropped and recreated (CREATE OR REPLACE
    cannot change the return type), which resets its comment; an identical comment on
    both sides must still be re-emitted.
    """
    gen_setup.assert_diff(
        src=[
            "CREATE FUNCTION g() RETURNS integer LANGUAGE sql AS 'SELECT 1'",
            "COMMENT ON FUNCTION g() IS 'hi'",
        ],
        dst=[
            "CREATE FUNCTION g() RETURNS bigint LANGUAGE sql AS 'SELECT 1'",
            "COMMENT ON FUNCTION g() IS 'hi'",
        ],
        diff=[
            'DROP FUNCTION "public"."g"()',
            "CREATE OR REPLACE FUNCTION public.g()\n RETURNS bigint\n LANGUAGE sql\nAS $function$SELECT 1$function$",
            'COMMENT ON FUNCTION "public"."g"() IS \'hi\'',
        ],
    )
