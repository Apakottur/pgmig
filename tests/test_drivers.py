from pgmig._drivers import DbDriver, resolve_driver


def test_auto_resolves_to_a_concrete_driver() -> None:
    # AUTO must never survive resolution: it is a request to choose, not a driver.
    assert resolve_driver(DbDriver.AUTO) is DbDriver.PSYCOPG


def test_an_explicit_driver_is_kept() -> None:
    assert resolve_driver(DbDriver.PSYCOPG) is DbDriver.PSYCOPG
