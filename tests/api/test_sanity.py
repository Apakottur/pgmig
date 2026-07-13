from tests.fixtures.generate_setup import GenerateSetup


def test_generate_sanity(gen_setup: GenerateSetup) -> None:
    """
    Sanity test - no SQL is run on either DB so no migration SQL is generated.
    """
    # Run harmless SQL.
    result = gen_setup.src.execute("SELECT 1")
    assert result == [(1,)]
    result = gen_setup.dst.execute("SELECT 1")
    assert result == [(1,)]

    # Verify migration SQL is empty.
    gen_setup.assert_migration_sql("")
