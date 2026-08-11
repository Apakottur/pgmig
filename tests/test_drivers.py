from pgmig._drivers import DbDriver


def test_resolved_names_a_concrete_driver() -> None:
    # AUTO is a request to choose, so it must never survive resolution; a driver named
    # explicitly is kept, which is what pinning one means.
    assert DbDriver.AUTO.resolved is DbDriver.PSYCOPG
    assert DbDriver.PSYCOPG.resolved is DbDriver.PSYCOPG
