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

`pgmig generate` accepts:

| Option           | Description                                             |
| ---------------- | ------------------------------------------------------- |
| `--source`, `-s` | DSN of the source (current) database. **Required.**     |
| `--target`, `-t` | DSN of the target (desired) database. **Required.**     |
| `--output`, `-o` | Write the migration SQL to this file instead of stdout. |

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
