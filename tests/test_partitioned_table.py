from tests.fixtures.generate_setup import GenerateSetup


def test_constraint_on_partitioned_table_ignored(gen_setup: GenerateSetup) -> None:
    """
    A primary key on a partitioned table (relkind 'p') must not crash introspection.
    Partitioned tables are out of scope, so no SQL is generated for it.
    """
    gen_setup.dst.execute("CREATE TABLE events (id integer NOT NULL) PARTITION BY RANGE (id)")
    gen_setup.dst.execute("ALTER TABLE events ADD CONSTRAINT events_pkey PRIMARY KEY (id)")

    gen_setup.assert_migration_sql("")
