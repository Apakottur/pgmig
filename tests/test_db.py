import sys

import pytest
import shpyx
from pytest_mock import MockerFixture

from pgmig._db import DbConnection, DbConnInfo
from pgmig._drivers import DbDriver
from pgmig._errors import PgmigApiError


def test_importing_pgmig_does_not_import_asyncpg() -> None:
    # asyncpg is an optional extra, so pgmig must load without it.
    shpyx.run(f"{sys.executable} -c \"import sys, pgmig, pgmig._cli._cli; assert 'asyncpg' not in sys.modules\"")


async def test_connect_without_asyncpg_installed(mocker: MockerFixture) -> None:
    mocker.patch.dict(sys.modules, {"asyncpg": None})
    db_conn_info = DbConnInfo(dsn="postgresql://localhost/db", label="source", driver=DbDriver.ASYNCPG)

    with pytest.raises(PgmigApiError, match=r"Install the pgmig\[asyncpg\] extra"):
        async with DbConnection.connect(db_conn_info=db_conn_info):
            pass
