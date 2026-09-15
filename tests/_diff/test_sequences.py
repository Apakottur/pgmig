from pgmig._diff.sequences import _alter_statements, _sequence_tail
from pgmig._models import Sequence


def _sequence(
    *,
    unlogged: bool = False,
    data_type: str = "integer",
    start: int = 1,
    increment: int = 1,
    min_value: int = 1,
    max_value: int = 100,
    cache: int = 1,
    cycle: bool = False,
) -> Sequence:
    return Sequence(
        name="counter",
        data_type=data_type,
        start=start,
        increment=increment,
        min_value=min_value,
        max_value=max_value,
        cache=cache,
        cycle=cycle,
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


def test_tail_all_defaults_is_empty() -> None:
    """
    A sequence whose every parameter is a Postgres default renders no tail at all.
    """
    ascending_defaults = _sequence(data_type="bigint", start=1, min_value=1, max_value=9223372036854775807)
    assert _sequence_tail(ascending_defaults) == ""


def test_tail_keeps_narrower_type() -> None:
    """
    A non-bigint type keeps its AS clause, which is what restores the MINVALUE/MAXVALUE
    defaults that the omitted bounds rely on.
    """
    integer_defaults = _sequence(data_type="integer", min_value=1, max_value=2147483647)
    assert _sequence_tail(integer_defaults) == " AS integer"


def test_tail_descending_defaults_are_omitted() -> None:
    """
    A descending sequence defaults to type_min..-1 starting at -1, so only the increment shows.
    """
    descending = _sequence(data_type="integer", increment=-1, min_value=-2147483648, max_value=-1, start=-1)
    assert _sequence_tail(descending) == " AS integer INCREMENT BY -1"


def test_tail_descending_explicit_start() -> None:
    """
    A descending sequence's default start is its MAXVALUE, not the type's; a start that differs
    from the resolved maximum is emitted.
    """
    descending = _sequence(data_type="integer", increment=-1, min_value=-2147483648, max_value=-1, start=-5)
    assert _sequence_tail(descending) == " AS integer START WITH -5 INCREMENT BY -1"


def test_tail_descending_explicit_bounds() -> None:
    """
    Descending bounds that differ from the type-derived defaults are emitted.
    """
    descending = _sequence(data_type="integer", increment=-1, min_value=-100, max_value=-10, start=-10)
    assert _sequence_tail(descending) == " AS integer INCREMENT BY -1 MINVALUE -100 MAXVALUE -10"


def test_tail_non_default_cache_and_cycle() -> None:
    """
    A non-1 cache and an enabled cycle are both emitted.
    """
    cached = _sequence(data_type="bigint", max_value=9223372036854775807, cache=20, cycle=True)
    assert _sequence_tail(cached) == " CACHE 20 CYCLE"
