from pgmig._drivers import DbDriver


def test_db_driver_resolve() -> None:
    for driver in DbDriver:
        resolved = driver.resolved

        match driver:
            case DbDriver.AUTO:
                assert resolved is DbDriver.PSYCOPG
            case DbDriver.PSYCOPG:
                assert resolved is DbDriver.PSYCOPG
            case DbDriver.ASYNCPG:
                assert resolved is DbDriver.ASYNCPG
