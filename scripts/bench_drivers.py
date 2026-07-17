"""
Benchmark the psycopg and asyncpg drivers on a full introspection of a populated database.

Run from the worktree:  uv run python scripts/bench_drivers.py
"""
# ruff: noqa: INP001, S608  (throwaway benchmark script, hardcoded DDL)

import asyncio
import statistics
import time

from pgmig._db import DbConnection
from pgmig._introspect._engine import introspect_db

_DSN_PREFIX = "postgresql://pgmig:pgmig@localhost:15432"
_ADMIN_DSN = f"{_DSN_PREFIX}/postgres"
_BENCH_DB = "pgmig_bench"
_BENCH_DSN = f"{_DSN_PREFIX}/{_BENCH_DB}"

_TABLES = 40
_VIEWS = 15
_ITERATIONS = 25


async def _recreate_bench_db() -> None:
    async with DbConnection.connect(dsn=_ADMIN_DSN, driver="psycopg") as admin:
        await admin.execute(f"DROP DATABASE IF EXISTS {_BENCH_DB} WITH (FORCE)")
        await admin.execute(f"CREATE DATABASE {_BENCH_DB}")


async def _populate() -> None:
    stmts: list[str] = ["CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy')"]
    for i in range(_TABLES):
        stmts.append(
            f"CREATE TABLE t{i} ("
            f"id bigint PRIMARY KEY, name text NOT NULL, val numeric(10, 2), "
            f"created timestamptz DEFAULT now(), feeling mood)"
        )
        stmts.append(f"CREATE INDEX t{i}_name_idx ON t{i} (name)")
    stmts.extend(f"CREATE VIEW v{i} AS SELECT id, name FROM t{i}" for i in range(_VIEWS))
    stmts.append("CREATE FUNCTION add(a integer, b integer) RETURNS integer LANGUAGE sql AS 'SELECT a + b'")

    async with DbConnection.connect(dsn=_BENCH_DSN, driver="psycopg") as conn:
        await conn.execute(";\n".join(stmts))


async def _time_driver(driver: str) -> list[float]:
    # Warm up (connection setup, prepared-statement caches) before timing.
    await introspect_db(_BENCH_DSN, driver)  # type: ignore[arg-type]

    timings: list[float] = []
    for _ in range(_ITERATIONS):
        start = time.perf_counter()
        await introspect_db(_BENCH_DSN, driver)  # type: ignore[arg-type]
        timings.append(time.perf_counter() - start)
    return timings


async def main() -> None:
    await _recreate_bench_db()
    await _populate()

    print(f"Introspecting {_TABLES} tables + {_VIEWS} views, {_ITERATIONS} iterations each.\n")
    print(f"{'driver':<10}{'mean (ms)':>12}{'min (ms)':>12}{'median (ms)':>14}")
    results: dict[str, float] = {}
    for driver in ("psycopg", "asyncpg"):
        timings = await _time_driver(driver)
        mean_ms = statistics.mean(timings) * 1000
        results[driver] = mean_ms
        print(f"{driver:<10}{mean_ms:>12.2f}{min(timings) * 1000:>12.2f}{statistics.median(timings) * 1000:>14.2f}")

    faster = min(results, key=lambda k: results[k])
    slower = max(results, key=lambda k: results[k])
    ratio = results[slower] / results[faster]
    print(f"\n{faster} is {ratio:.2f}x faster than {slower} (mean).")


if __name__ == "__main__":
    asyncio.run(main())
