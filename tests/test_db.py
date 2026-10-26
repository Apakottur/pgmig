import importlib
import sys

import pytest
from pytest_mock import MockerFixture

from pgmig._db import DbConnection
from pgmig._drivers import DbConnInfo, DbDriver
from pgmig._errors import PgmigApiError


def test_pgmig_imports_without_asyncpg(mocker: MockerFixture) -> None:
    # asyncpg is an optional extra, so pgmig must load without it. Block asyncpg and drop the loaded pgmig modules, so
    # that importing pgmig runs all of its imports afresh. patch.dict restores the modules afterwards.
    mocker.patch.dict(sys.modules, {"asyncpg": None})
    for name in [name for name in sys.modules if name.split(".")[0] == "pgmig"]:
        del sys.modules[name]

    importlib.import_module("pgmig._cli._cli")


async def test_connect_without_asyncpg_installed(mocker: MockerFixture) -> None:
    # Block asyncpg and unload pgmig's asyncpg module, in case an earlier test loaded it.
    mocker.patch.dict(sys.modules, {"asyncpg": None})
    sys.modules.pop("pgmig._asyncpg", None)
    db_conn_info = DbConnInfo(dsn="postgresql://localhost/db", label="source", driver=DbDriver.ASYNCPG)

    with pytest.raises(PgmigApiError, match=r"Install the pgmig\[asyncpg\] extra"):
        async with DbConnection.connect(db_conn_info=db_conn_info):
            pass
