<p align="center">
  <img src="https://github.com/Apakottur/pgmig/blob/main/pgmig.png?raw=true" width="400" />
</p>

[![image](https://img.shields.io/pypi/v/pgmig.svg)](https://pypi.python.org/pypi/pgmig)
[![image](https://img.shields.io/pypi/l/pgmig.svg)](https://github.com/Apakottur/pgmig/blob/main/LICENSE)
[![image](https://img.shields.io/pypi/pyversions/pgmig.svg)](https://pypi.python.org/pypi/pgmig)

`pgmig` generates schema migrations between Postgres databases.

Point it at two databases and it returns the SQL that migrates the schema of one
to match the other — tables, indexes, extensions, functions, and so on. The
comparison is read-only; `pgmig` never modifies your databases, it only hands
you the SQL to run.

## Installation

```shell
pip install pgmig
```

## Usage

`generate` takes two connection strings and returns a string of SQL that, when
applied to `source`, makes its schema match `target`:

```python
import pgmig

sql = pgmig.generate(
    source="postgresql://user:pass@localhost:5432/current",
    target="postgresql://user:pass@localhost:5432/desired",
)

print(sql)  # the migration SQL — run it yourself against `source`
```

`source` and `target` are keyword-only. When the two schemas already match,
`generate` returns an empty string. `pgmig` opens read-only connections to both
databases and never runs the generated SQL for you.

## Local development

Dependencies are managed with [uv](https://docs.astral.sh/uv/):

```shell
uv sync
```

### Tests

Tests run against a real Postgres instance, started automatically in a container
via `docker compose`, so a running **Docker daemon is required**:

```shell
uv run pytest -c tests/pytest.ini tests
```

This enforces 100% branch coverage. Note that a bare `uv run pytest` (without
`-c tests/pytest.ini tests`) does not pick up the config and silently skips the
coverage gate.

### Linters

Linters and formatters run through pre-commit:

```shell
uv run pre-commit run -a
```

### Type checks

```shell
uv run mypy --config-file linters/mypy.toml src tests
uv run ty check --config-file linters/ty.toml src tests
```

### Releasing

An interactive script tags a new version, which triggers the release workflow
(build + publish to PyPI + GitHub Release):

```shell
uv run ./scripts/release.py
```
