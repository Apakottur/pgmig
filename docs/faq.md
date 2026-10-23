# FAQ

## Which build should I install?

pgmig talks to Postgres through the psycopg driver. The base `pgmig` install uses its pure
Python build; extras swap in a faster one. The migration code is identical, only the connection
layer changes.

| Install                         | Build                 | Needs at install           | libpq        | Notes |
| ------------------------------- | --------------------- | -------------------------- | ------------ | ----- |
| `pip install pgmig`             | psycopg (pure Python) | nothing                    | system libpq | Works everywhere; slowest. |
| `pip install 'pgmig[binary]'`   | psycopg (prebuilt C)  | nothing                    | **bundled**  | Fast, no build tools or system libpq. Bundled libpq/OpenSSL only update with the wheel, so psycopg advises against it in production — ideal for CLI / standalone use. |
| `pip install 'pgmig[c]'`        | psycopg (compiled C)  | C compiler + libpq headers | system libpq | Fast **and** rides your OS's libpq security updates. Recommended for production. |

## Do I need libpq installed?

Depends on the install. The base install and the `c` extra use the system libpq (install it via
your OS, e.g. `apt install libpq5`). The `binary` extra bundles its own, so it needs nothing
extra on the machine.
