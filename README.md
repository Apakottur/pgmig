<p align="center">
  <img src="https://github.com/Apakottur/pgmig/blob/main/pgmig.png?raw=true" width="400" />
</p>

[![image](https://img.shields.io/pypi/v/pgmig.svg)](https://pypi.python.org/pypi/pgmig)
[![image](https://img.shields.io/pypi/l/pgmig.svg)](https://github.com/Apakottur/pgmig/blob/main/LICENSE)
[![image](https://img.shields.io/pypi/pyversions/pgmig.svg)](https://pypi.python.org/pypi/pgmig)

Generate migrations between Postgres databases.

## Installation

```shell
pip install pgmig
```

## Usage

### Schema migration

Get the SQL that, when applied to `source`, makes its schema match `target`:

```python
import pgmig

sql = pgmig.generate(
    source="postgresql://user:pass@localhost:5432/current",
    target="postgresql://user:pass@localhost:5432/desired",
)

print(sql)  # the migration SQL — run it yourself against `source`
```

When the two schemas already match,
`generate` returns an empty string. `pgmig` opens read-only connections to both
databases and never runs the generated SQL for you.

## Contributing

To contribute simply open a PR with your changes.

All checks (Linters, type checks and tests) automatically run in CI through GitHub Actions.

### Running checks locally

Local development is done with [uv](https://docs.astral.sh/uv/getting-started/installation/).

Start by installing all the development dependencies:

```shell
uv sync
```

To run the linters use `pre-commit`:

```shell
pre-commit run -a
```

To run the unit tests use `pytest`:

```shell
pytest -c tests/pytest.ini tests
```

To run type checks use `mypy` or `ty` (both are run in CI):

```shell
mypy --config-file linters/mypy.toml src tests
ty check --config-file linters/ty.toml src tests
```

### Releasing

To release a new version, run the interactive script:

```shell
./scripts/release.py
```
