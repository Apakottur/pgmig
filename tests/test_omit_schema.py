import pytest
from psycopg import sql

from pgmig import PgmigError, generate
from tests.fixtures.generate_setup import GenerateSetup
from tests.utils.db_utils import _KEY, get_unique_db_name


def test_omit_schema_table_and_column(gen_setup: GenerateSetup) -> None:
    """
    With omit_schema, a pgmig-built object path (CREATE TABLE, COMMENT ON COLUMN) drops
    the schema qualifier that the default output carries.
    """
    gen_setup.dst.execute("CREATE TABLE person (name text)")
    gen_setup.dst.execute("COMMENT ON COLUMN person.name IS 'the name'")

    gen_setup.assert_migration_sql(
        [
            'CREATE TABLE "person" ("name" text);',
            'COMMENT ON COLUMN "person"."name" IS \'the name\';',
        ],
        omit_schema="public",
    )


def test_omit_schema_strips_from_server_definitions(gen_setup: GenerateSetup) -> None:
    """
    The qualifier is stripped even inside server-generated definition strings: the
    search_path leg strips what Postgres deparse resolves (FK REFERENCES, the trigger's
    EXECUTE FUNCTION, view/matview bodies), and the textual leg handles the spots
    deparse always qualifies (index/trigger ON clause, the routine's own header name).
    The whole migration must also converge.
    """
    gen_setup.execute_both("CREATE TABLE team (id integer PRIMARY KEY)")
    gen_setup.execute_both("CREATE TABLE person (id integer, team_id integer)")

    # Objects on the target only, spanning every server-generated definition kind.
    gen_setup.dst.execute("CREATE INDEX person_id_idx ON person (id)")
    gen_setup.dst.execute("ALTER TABLE person ADD CONSTRAINT person_team_fk FOREIGN KEY (team_id) REFERENCES team (id)")
    gen_setup.dst.execute("CREATE FUNCTION bump(n integer) RETURNS integer LANGUAGE sql AS $$ SELECT n + 1 $$")
    gen_setup.dst.execute("CREATE FUNCTION touch() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$")
    gen_setup.dst.execute("CREATE TRIGGER person_touch BEFORE INSERT ON person FOR EACH ROW EXECUTE FUNCTION touch()")

    result = generate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn, omit_schema="public")

    # No schema qualifier survives anywhere (quoted or bare), and the objects are still named.
    assert "public" not in result, f"Qualifier leaked:\n{result}"
    assert "person_id_idx" in result
    assert "person_team_fk" in result
    assert "bump" in result
    assert "person_touch" in result

    # Applying the migration makes the source match the target (converges to no diff).
    gen_setup.src.execute(result)  # ty: ignore[invalid-argument-type]
    residual = generate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn, omit_schema="public")
    assert residual == "", f"Migration did not converge. Residual:\n{residual}"


def test_omit_schema_covers_all_object_kinds(gen_setup: GenerateSetup) -> None:
    """
    Every emitted object path honors omit_schema: views, materialized views, domains,
    composite types, enums, sequences and table ownership -- not just tables/indexes.
    """
    role = get_unique_db_name("pgmig_omit_owner", _KEY)
    gen_setup.src.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
    gen_setup.src.execute(sql.SQL("CREATE ROLE {}").format(sql.Identifier(role)))

    gen_setup.execute_both("CREATE TABLE person (id integer)")
    # Owner differs: source default (pgmig), target the created role.
    gen_setup.dst.execute(sql.SQL("ALTER TABLE person OWNER TO {}").format(sql.Identifier(role)))

    # Target-only objects of every remaining kind.
    gen_setup.dst.execute("CREATE VIEW person_view AS SELECT id FROM person")
    gen_setup.dst.execute("CREATE MATERIALIZED VIEW person_mat AS SELECT id FROM person")
    gen_setup.dst.execute("CREATE DOMAIN nonempty AS text CHECK (VALUE <> '')")
    gen_setup.dst.execute("CREATE TYPE pair AS (x integer, y integer)")
    gen_setup.dst.execute("CREATE TYPE mood AS ENUM ('happy')")
    gen_setup.dst.execute("CREATE SEQUENCE counter")

    result = generate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn, omit_schema="public")

    assert "public" not in result, f"Qualifier leaked:\n{result}"
    for name in ("person_view", "person_mat", "nonempty", "pair", "mood", "counter", role):
        assert name in result, f"Object missing from migration: {name}\n{result}"

    gen_setup.src.execute(result)  # ty: ignore[invalid-argument-type]
    residual = generate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn, omit_schema="public")
    assert residual == "", f"Migration did not converge. Residual:\n{residual}"


def test_omit_schema_none_keeps_qualifier(gen_setup: GenerateSetup) -> None:
    """
    omit_schema=None (the default) leaves the schema fully qualified.
    """
    gen_setup.dst.execute("CREATE TABLE person (name text)")

    gen_setup.assert_migration_sql('CREATE TABLE "public"."person" ("name" text);', omit_schema=None)


def test_omit_schema_rejects_extra_schema(gen_setup: GenerateSetup) -> None:
    """
    A second user schema present makes the omitted qualifier ambiguous -> PgmigError.
    """
    gen_setup.execute_both("CREATE SCHEMA extra")

    with pytest.raises(PgmigError, match="exactly that one user schema"):
        generate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn, omit_schema="public")


def test_omit_schema_rejects_wrong_name(gen_setup: GenerateSetup) -> None:
    """
    Naming a schema that is not the sole user schema (here: absent) -> PgmigError.
    """
    with pytest.raises(PgmigError, match="exactly that one user schema"):
        generate(source=gen_setup.src.dsn, target=gen_setup.dst.dsn, omit_schema="nope")
