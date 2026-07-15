from tests._api.generate_setup import GenerateSetup


def test_range_type_raises_not_supported(gen_setup: GenerateSetup) -> None:
    """
    A range type (pg_type typtype 'r') is not modelled yet and must raise.
    """
    gen_setup.assert_unsupported(
        src=[],
        dst=["CREATE TYPE float_range AS RANGE (subtype = float8)"],
        match=r"range type .* is not supported",
    )


def test_instead_of_trigger_on_view_raises_not_supported(gen_setup: GenerateSetup) -> None:
    """
    An INSTEAD OF trigger on a view (pg_trigger on relkind 'v') is not modelled and must raise
    rather than let generate() silently ignore it.
    """
    gen_setup.assert_unsupported(
        src=[],
        dst=[
            "CREATE VIEW v AS SELECT 1 AS n",
            "CREATE FUNCTION v_trig() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RETURN NEW; END;$$",
            "CREATE TRIGGER v_ins INSTEAD OF INSERT ON v FOR EACH ROW EXECUTE FUNCTION v_trig()",
        ],
        match=r"INSTEAD OF trigger .* is not supported",
    )


def test_rule_raises_not_supported(gen_setup: GenerateSetup) -> None:
    """
    A user rule (pg_rewrite, not a view's auto _RETURN rule) is not modelled and must raise.
    """
    gen_setup.assert_unsupported(
        src=[],
        dst=["CREATE TABLE t (n integer)", "CREATE RULE t_no_insert AS ON INSERT TO t DO INSTEAD NOTHING"],
        match=r"rule .* is not supported",
    )


def test_view_return_rule_not_reported(gen_setup: GenerateSetup) -> None:
    """
    A view's own auto _RETURN rule is not a user rule: a plain view diffs normally, without
    the rule guard tripping.
    """
   await gen_setup.assert_diff(
        src=[],
        dst=["CREATE VIEW v AS SELECT 1 AS n"],
        diff=['CREATE VIEW "public"."v" AS SELECT 1 AS n'],
    )


def test_rls_policy_raises_not_supported(gen_setup: GenerateSetup) -> None:
    """
    A row-level security policy (pg_policy) is not modelled and must raise.
    """
    gen_setup.assert_unsupported(
        src=[],
        dst=["CREATE TABLE t (n integer)", "CREATE POLICY t_pol ON t USING (true)"],
        match=r"row-level security policy .* is not supported",
    )


def test_rls_enabled_table_raises_not_supported(gen_setup: GenerateSetup) -> None:
    """
    A table with row-level security enabled but no policy (pg_class.relrowsecurity) changes
    access semantics that are not modelled, so it must raise rather than converge silently.
    """
    gen_setup.assert_unsupported(
        src=[],
        dst=["CREATE TABLE t (n integer)", "ALTER TABLE t ENABLE ROW LEVEL SECURITY"],
        match=r"row-level security .* is not supported",
    )


def test_base_type_raises_not_supported(gen_setup: GenerateSetup) -> None:
    """
    A user base type (pg_type typtype 'b') is not modelled and must raise. Built via the
    internal-I/O-function trick so no C code is needed.
    """
    gen_setup.assert_unsupported(
        src=[],
        dst=[
            "CREATE TYPE mytype",
            "CREATE FUNCTION mytype_in(cstring) RETURNS mytype AS 'textin' LANGUAGE internal IMMUTABLE STRICT",
            "CREATE FUNCTION mytype_out(mytype) RETURNS cstring AS 'textout' LANGUAGE internal IMMUTABLE STRICT",
            "CREATE TYPE mytype (INPUT = mytype_in, OUTPUT = mytype_out, LIKE = text)",
        ],
        match=r"base type .* is not supported",
    )


def test_enum_array_type_not_reported(gen_setup: GenerateSetup) -> None:
    """
    A user type auto-creates an array type (typtype 'b', typcategory 'A'). That array must
    not be mistaken for an unsupported base type: a plain enum diffs normally.
    """
   await gen_setup.assert_diff(
        src=[],
        dst=["CREATE TYPE color AS ENUM ('r', 'g')"],
        diff=["CREATE TYPE \"public\".\"color\" AS ENUM ('r', 'g')"],
    )


def test_inheritance_child_raises_not_supported(gen_setup: GenerateSetup) -> None:
    """
    A legacy INHERITS child (parent is an ordinary table, not a partitioned one) would be
    re-emitted as a standalone table, silently dropping the inheritance. It is not modelled
    and must raise. Partition children (parent relkind 'p') are unaffected.
    """
    gen_setup.assert_unsupported(
        src=[],
        dst=["CREATE TABLE parent (n integer)", "CREATE TABLE child () INHERITS (parent)"],
        match=r"inheritance child .* is not supported",
    )


def test_extended_statistics_raises_not_supported(gen_setup: GenerateSetup) -> None:
    """
    An extended statistics object (pg_statistic_ext, CREATE STATISTICS) is not modelled and
    must raise.
    """
    gen_setup.assert_unsupported(
        src=[],
        dst=["CREATE TABLE t (a integer, b integer)", "CREATE STATISTICS t_stats ON a, b FROM t"],
        match=r"extended statistics .* is not supported",
    )


def test_event_trigger_raises_not_supported(gen_setup: GenerateSetup) -> None:
    """
    An event trigger (pg_event_trigger) is database-global with no schema, so it exercises
    the schema-less reporting path. It is not modelled and must raise.
    """
    gen_setup.assert_unsupported(
        src=[],
        dst=[
            "CREATE FUNCTION et_fn() RETURNS event_trigger LANGUAGE plpgsql AS $$BEGIN END;$$",
            "CREATE EVENT TRIGGER et ON ddl_command_start EXECUTE FUNCTION et_fn()",
        ],
        match=r'event trigger "et" is not supported',
    )
