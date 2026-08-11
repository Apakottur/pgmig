from pgmig._drivers import DbDriver


def test_db_driver_resolve() -> None:
    for driver in DbDriver:
        match driver:
            case DbDriver.AUTO:
                assert driver.resolved is DbDriver.PSYCOPG
            case DbDriver.PSYCOPG:
                assert driver.resolved is DbDriver.PSYCOPG
