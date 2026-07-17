from tests.fixtures.db_utils import _MAX_IDENTIFIER_LEN, get_unique_postgres_name


def test_simple_branch() -> None:
    assert get_unique_postgres_name("pgmig_src", "main") == "pgmig_src_main"


def test_slashes_and_dashes_become_underscores() -> None:
    assert get_unique_postgres_name("pgmig_src", "test/verify-migration") == "pgmig_src_test_verify_migration"


def test_uppercase_lowercased() -> None:
    assert get_unique_postgres_name("pgmig_dst", "Feature/ABC") == "pgmig_dst_feature_abc"


def test_leading_trailing_separators_stripped() -> None:
    assert get_unique_postgres_name("pgmig_src", "/foo/") == "pgmig_src_foo"


def test_collapses_runs_of_separators() -> None:
    assert get_unique_postgres_name("pgmig_src", "a---b__c") == "pgmig_src_a_b_c"


def test_long_name_truncated_within_limit() -> None:
    key = "x" * 100
    name = get_unique_postgres_name("pgmig_src", key)
    assert len(name) <= _MAX_IDENTIFIER_LEN


def test_long_names_stay_unique_by_hash() -> None:
    a = get_unique_postgres_name("pgmig_src", "feature/" + "a" * 100)
    b = get_unique_postgres_name("pgmig_src", "feature/" + "b" * 100)
    assert a != b
    assert len(a) <= _MAX_IDENTIFIER_LEN
    assert len(b) <= _MAX_IDENTIFIER_LEN


def test_deterministic() -> None:
    assert get_unique_postgres_name("pgmig_src", "some/branch") == get_unique_postgres_name("pgmig_src", "some/branch")
