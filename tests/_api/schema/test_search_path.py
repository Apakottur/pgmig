from tests._api.generate_setup import GenerateSetup
from tests.fixtures.db_utils import SRC_DB


def test_identical_dbs_with_source_search_path_setting(gen_setup: GenerateSetup) -> None:
    """
    Two byte-identical databases must produce no diff even when one of them pins a
    non-default search_path. Introspection must not depend on the DB's search_path.
    """
    gen_setup.assert_diff(
        src=[
            # Source database pins an empty search_path (a common hardened setup); new connections inherit it.
            f"ALTER DATABASE {SRC_DB} SET search_path = ''",
        ],
        dst=[],
        both=[
            "CREATE TYPE mood AS ENUM ('happy', 'sad')",
            "CREATE TABLE person (m mood)",
        ],
        diff=[],
    )


def test_column_type_is_schema_qualified(gen_setup: GenerateSetup) -> None:
    """
    A non-built-in (schema-qualified) type is emitted fully qualified, so the output
    applies under any search_path (e.g. a runner that sets search_path = '').
    """
    gen_setup.assert_diff(
        src=[],
        dst=["CREATE TYPE mood AS ENUM ('happy', 'sad')", "CREATE TABLE person (m mood)"],
        diff=[
            "CREATE TYPE \"public\".\"mood\" AS ENUM ('happy', 'sad')",
            'CREATE TABLE "public"."person" ("m" public.mood)',
        ],
    )
