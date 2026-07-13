<p align="center">
  <img src="https://github.com/Apakottur/pgmig/blob/main/pgmig.png?raw=true" width="400" />
</p>

[![image](https://img.shields.io/pypi/v/pgmig.svg)](https://pypi.python.org/pypi/pgmig)
[![image](https://img.shields.io/pypi/l/pgmig.svg)](https://github.com/Apakottur/pgmig/blob/main/LICENSE)
[![image](https://img.shields.io/pypi/pyversions/pgmig.svg)](https://pypi.python.org/pypi/pgmig)

Generate migrations between Postgres databases.

Use `pgmig` to compare the structure of two Postgres databases — a `source` and a `target` — and generate
the SQL that turns the source into the target.

`pgmig` connects **read-only** to both databases and never
runs the generated SQL for you: you review it and apply it yourself.

pgmig officially supports **Postgres 14–18** — the majors currently maintained upstream — and is
tested against each in CI. Other versions may work but are not tested.

This project is currently in active development, see [Roadmap](https://github.com/Apakottur/pgmig/issues/8).

## Table of Contents

1. [Getting Started](#getting-started)
2. [Configuration](#configuration)
3. [Contributing](#contributing)
4. [License](#license)

## Getting Started

### Installation

pgmig is available as [`pgmig`](https://pypi.org/project/pgmig/) on PyPI.

Invoke pgmig directly with [`uvx`](https://docs.astral.sh/uv/):

```shell
uvx pgmig generate \
  --source postgresql://user:pass@localhost:5432/current \
  --target postgresql://user:pass@localhost:5432/desired
```

Or install pgmig with `uv` (recommended) or `pip`:

```shell
# With uv.
uv tool install pgmig@latest  # Install pgmig globally.
uv add --dev pgmig            # Or add pgmig to your project.

# With pip.
pip install pgmig
```

### Usage

`pgmig` can be used directly in the command line or as a Python library.

#### Command line

Print the migration SQL that makes `source` match `target`:

```shell
pgmig generate \
  --source postgresql://user:pass@localhost:5432/current \
  --target postgresql://user:pass@localhost:5432/desired
```

When the two structures already match, nothing is printed.

#### Library

The same diff is available as a function that returns the SQL as a string:

```python
import pgmig

sql = pgmig.generate(
    source="postgresql://user:pass@localhost:5432/current",
    target="postgresql://user:pass@localhost:5432/desired",
)

print(sql)  # the migration SQL
```

`generate` returns an empty string when the structures already match.

## Configuration

`pgmig` has no configuration file — everything is passed on the command line (or as arguments to `pgmig.generate`).

The CLI (`pgmig generate`) and the library (`pgmig.generate`) share the same options; the CLI
adds a few more (`—` in the library column):

| CLI option               | Library argument     | Description                                             |
| ------------------------ | -------------------- | ------------------------------------------------------- |
| `--source`, `-s`         | `source`             | DSN of the source (current) database. Falls back to the `PGMIG_SOURCE` environment variable. |
| `--target`, `-t`         | `target`             | DSN of the target (desired) database. Falls back to the `PGMIG_TARGET` environment variable. |
| `--index-concurrently`, `-C` | `index_concurrently` | Whether to emit `CREATE`/`DROP INDEX` (including `CREATE UNIQUE INDEX`) with `CONCURRENTLY`. Using `CONCURRENTLY` avoids blocking index read/write operations, but takes longer to execute and cannot be run inside a transaction block. |
| `--ignore-extension-version` | `ignore_extension_version` | Names of extensions whose version mismatch is ignored: no `ALTER EXTENSION ... UPDATE TO` is emitted for them. Repeatable on the CLI; a list of names in the library. |
| `--omit-schema`          | `omit_schema`        | Omit this schema's qualifier from the emitted SQL for a more readable diff. Requires it to be the only user schema in both databases. |
| `--output`, `-o`         | —                    | Write the migration SQL to this file instead of stdout. |
| `--check`, `-c`          | —                    | Exit non-zero if the databases differ (CI gate); the migration is still emitted. |

### Connections

Each DSN can be passed as a flag or through its environment variable; an explicit flag wins.
Command-line arguments are visible in `ps` output and shell history, so prefer the environment
variables for anything containing secrets — for example, in CI:

```yaml
- run: pgmig generate --check
  env:
    PGMIG_SOURCE: ${{ secrets.PROD_DATABASE_URL }}
    PGMIG_TARGET: postgresql://postgres:postgres@localhost:5432/desired
```

Other commands:

| Command           | Description                  |
| ----------------- | ---------------------------- |
| `pgmig --version` | Print the installed version. |
| `pgmig --help`    | Show help for any command.   |

A DSN is any [libpq connection string](https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNSTRING),
e.g. `postgresql://user:pass@host:5432/dbname`.

## Contributing

Contributions are welcome!

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

`pgmig` is distributed under the terms of the [MIT license](LICENSE).
