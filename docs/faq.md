# FAQ

## Which build should I install?

pgmig talks to Postgres through a driver. The base `pgmig` install uses **psycopg** (pure
Python); extras swap in a faster build or a different driver. The migration code is identical,
only the connection layer changes.

| Install                         | Build                 | Needs at install           | libpq        | Notes |
| ------------------------------- | --------------------- | -------------------------- | ------------ | ----- |
| `pip install pgmig`             | psycopg (pure Python) | nothing                    | system libpq | Works everywhere; slowest. |
| `pip install 'pgmig[binary]'`   | psycopg (prebuilt C)  | nothing                    | **bundled**  | Fast, no build tools or system libpq. Bundled libpq/OpenSSL only update with the wheel, so psycopg advises against it in production — ideal for CLI / standalone use. |
| `pip install 'pgmig[c]'`        | psycopg (compiled C)  | C compiler + libpq headers | system libpq | Fast **and** rides your OS's libpq security updates. Recommended for production. |
| `pip install 'pgmig[asyncpg]'`  | asyncpg               | nothing                    | **none**     | No libpq at all. Select it with `--driver asyncpg` (or `driver="asyncpg"`). |

## Do I need libpq installed?

Depends on the install. The base install and the `c` extra use the system libpq (install it via
your OS, e.g. `apt install libpq5`). The `binary` extra bundles its own, and the `asyncpg` extra
doesn't use libpq at all — so either of those needs nothing extra on the machine.

## Can I use asyncpg instead of psycopg?

Yes. Install the extra and select the driver:

```shell
pip install 'pgmig[asyncpg]'
pgmig generate -s "$SRC" -t "$TGT" --driver asyncpg   # or set PGMIG_DRIVER=asyncpg
```

In the library, pass `driver="asyncpg"` to `generate` / `agenerate`. The default is `psycopg`.

## Which driver is fastest?

They are level for pgmig's workload. Introspection is a handful of one-shot catalog queries,
where asyncpg's per-statement prepare cost cancels out its throughput edge, and psycopg's `c` /
`binary` builds would push it further ahead. A generation finishes in well under a second either
way, so pick by install convenience rather than speed.
