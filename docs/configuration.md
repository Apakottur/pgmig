# Configuration

`pgmig` has no configuration file — everything is passed on the command line (or as arguments to
[`pgmig.generate`](reference/api.md#pgmig.generate)).

The CLI (`pgmig generate`) and the library ([`pgmig.generate`](reference/api.md#pgmig.generate) and its async
twin [`pgmig.agenerate`](reference/api.md#pgmig.agenerate)) share the same options; the CLI adds a few more (`—`
in the library column):

| CLI option               | Library argument     | Description                                             |
| ------------------------ | -------------------- | ------------------------------------------------------- |
| `--source`, `-s`         | `source`             | DSN of the source (current) database. Falls back to the `PGMIG_SOURCE` environment variable. |
| `--target`, `-t`         | `target`             | DSN of the target (desired) database. Falls back to the `PGMIG_TARGET` environment variable. |
| `--index-concurrently`     | `index_concurrently` | Whether to emit `CREATE`/`DROP INDEX` (including `CREATE UNIQUE INDEX`) with `CONCURRENTLY`. Using `CONCURRENTLY` avoids blocking index read/write operations, but takes longer to execute and cannot be run inside a transaction block. |
| `--safe-not-null`        | `safe_not_null`      | Whether to emit `SET NOT NULL` on an existing column through a `CHECK (col IS NOT NULL)` constraint that is added `NOT VALID`, validated, and dropped once the column is `NOT NULL`. Plain `SET NOT NULL` scans the whole table under an `ACCESS EXCLUSIVE` lock; validating the `CHECK` scans under a lock that does not block reads or writes, and lets `SET NOT NULL` skip its scan. Run the statements outside a transaction block, otherwise the lock taken by the first one is held throughout. |
| `--ignore-extension-version` | `ignore_extension_version` | Names of extensions whose version mismatch is ignored: no `ALTER EXTENSION ... UPDATE TO` is emitted for them. Repeatable on the CLI; a list of names in the library. |
| `--ignore-schema`         | `ignore_schemas`     | Schema names to exclude from the diff entirely: their tables and every other object, and the `CREATE`/`DROP` of the schema itself, are ignored (even object kinds pgmig cannot otherwise process). The schema must be isolated — if it shares any dependency with a kept schema (a foreign key, a view read, a cross-schema type, …), pgmig errors rather than emit a migration that would fail at apply. Repeatable on the CLI; a list of names in the library. |
| `--include-owner`        | `include_owner`      | Emit `ALTER ... OWNER TO` statements to reconcile ownership. Off by default: ownership references cluster-level roles that routinely differ across environments, so it is not part of the default convergence. |
| `--include-grants`       | `include_grants`     | Also emit named-role `GRANT`/`REVOKE`. `PUBLIC` grants are always diffed (portable and apply-safe); named-role grants reference cluster-level roles that diverge across environments and fail on apply when the role is absent on the target, so they are opt-in. |
| `--driver`               | `driver`             | Database driver to connect with: `auto` (default), `psycopg` or `asyncpg`. `auto` picks among the installed drivers; naming one pins it. On the CLI it falls back to the `PGMIG_DRIVER` environment variable. See [the FAQ](faq.md#which-build-should-i-install). |
| `--output`, `-o`         | —                    | Write the migration SQL to this file instead of stdout. |
| `--check`, `-c`          | —                    | Exit non-zero if the databases differ (CI gate); the migration is still emitted. |

## Connections

Each DSN can be passed as a flag or through its environment variable; an explicit flag wins.
Command-line arguments are visible in `ps` output and shell history, so prefer the environment
variables for anything containing secrets — for example, in CI:

```yaml
- run: pgmig generate --check
  env:
    PGMIG_SOURCE: ${{ secrets.PROD_DATABASE_URL }}
    PGMIG_TARGET: postgresql://postgres:postgres@localhost:5432/desired
```

A DSN is any [libpq connection string](https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNSTRING),
e.g. `postgresql://user:pass@host:5432/dbname`.

## Exit codes

`pgmig generate` exits with:

| Code | Meaning                                                                                          |
| ---- | ------------------------------------------------------------------------------------------------ |
| `0`  | The migration was generated (or the databases already match).                                   |
| `1`  | An error occurred, or `--check` was passed and the databases differ.                             |
| `2`  | Invalid usage, e.g. `--source` or `--target` is missing and its environment variable is not set. |

Errors are printed to stderr, so stdout (or the `--output` file) only ever holds the migration SQL. When the
databases already match, nothing is printed and the `--output` file is left empty.

## Other commands

| Command           | Description                  |
| ----------------- | ---------------------------- |
| `pgmig --version` | Print the installed version. |
| `pgmig --help`    | Show help for any command.   |
