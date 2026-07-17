from pgmig._diff.sequences import _alter_statements, _persistence_keyword
from pgmig._models import Sequence


def _sequence(*, unlogged: bool = False, increment: int = 1) -> Sequence:
    """
    Build a standalone Sequence for the unit tests. UNLOGGED-sequence branches are exercised
    here (not against a live DB) so they are covered on the Postgres 14 CI leg, where the
    UNLOGGED SEQUENCE syntax does not exist.
    """
    return Sequence(
        name="counter",
        data_type="integer",
        start=1,
        increment=increment,
        min_value=1,
        max_value=100,
        cache=1,
        cycle=False,
        comment=None,
        owned_by=None,
        unlogged=unlogged,
    )


def test_persistence_keyword() -> None:
    """The UNLOGGED keyword prefixes CREATE only for an unlogged sequence."""
    assert _persistence_keyword(_sequence(unlogged=True)) == "UNLOGGED "
    assert _persistence_keyword(_sequence(unlogged=False)) == ""


def test_alter_flip_to_unlogged() -> None:
    """A logged->unlogged flip is a standalone ALTER SEQUENCE ... SET UNLOGGED."""
    src = _sequence(unlogged=False)
    dst = _sequence(unlogged=True)
    assert _alter_statements("public", "counter", src, dst) == ['ALTER SEQUENCE "public"."counter" SET UNLOGGED;']


def test_alter_flip_to_logged() -> None:
    """An unlogged->logged flip is a standalone ALTER SEQUENCE ... SET LOGGED."""
    src = _sequence(unlogged=True)
    dst = _sequence(unlogged=False)
    assert _alter_statements("public", "counter", src, dst) == ['ALTER SEQUENCE "public"."counter" SET LOGGED;']


def test_alter_option_and_persistence_are_separate_statements() -> None:
    """
    An option change and a persistence flip cannot be combined into one ALTER SEQUENCE, so
    they are emitted as two statements (options first, then the SET LOGGED/UNLOGGED).
    """
    src = _sequence(unlogged=False, increment=1)
    dst = _sequence(unlogged=True, increment=5)
    assert _alter_statements("public", "counter", src, dst) == [
        'ALTER SEQUENCE "public"."counter" INCREMENT BY 5;',
        'ALTER SEQUENCE "public"."counter" SET UNLOGGED;',
    ]


def test_alter_no_change() -> None:
    """No option or persistence difference -> no statements."""
    assert _alter_statements("public", "counter", _sequence(), _sequence()) == []
