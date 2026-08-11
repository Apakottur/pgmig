from pgmig._diff.sequences import _alter_statements
from pgmig._models import Sequence


def _sequence(*, unlogged: bool) -> Sequence:
    return Sequence(
        name="counter",
        data_type="integer",
        start=1,
        increment=1,
        min_value=1,
        max_value=100,
        cache=1,
        cycle=False,
        comment=None,
        owner="postgres",
        grants=frozenset(),
        owned_by=None,
        unlogged=unlogged,
    )


def test_alter_persistence_flip() -> None:
    """
    A persistence flip is a standalone ALTER SEQUENCE ... SET LOGGED / SET UNLOGGED.

    Covered here rather than only through the API because UNLOGGED sequences are PG15+: on the
    Postgres 14 CI leg the API tests skip (no unlogged sequence can exist), leaving this branch
    unreachable there, so this unit test keeps the 100% coverage gate green on that leg.
    """
    logged, unlogged = _sequence(unlogged=False), _sequence(unlogged=True)
    assert _alter_statements("public", "counter", logged, unlogged) == [
        'ALTER SEQUENCE "public"."counter" SET UNLOGGED;'
    ]
    assert _alter_statements("public", "counter", unlogged, logged) == ['ALTER SEQUENCE "public"."counter" SET LOGGED;']
