# Contributing to pgmig

Thanks for your interest in contributing! To contribute, open a pull request with your changes, or an
issue with your bug or request.

All checks (linters, type checks, and tests) run automatically in CI through GitHub Actions.

## Development environment

Local development is done with [uv](https://docs.astral.sh/uv/getting-started/installation/).

Install all the development dependencies:

```shell
uv sync
```

The tests spin up a Postgres instance with Docker, so a running Docker daemon is required.

## Running checks locally

Run the linters with `prek`:

```shell
uv run prek run -a
```

Run the unit tests with `pytest`:

```shell
uv run pytest -c tests/pytest.ini tests
```

Run the type checks with `mypy` and `ty` (both run in CI):

```shell
uv run mypy --config-file linters/mypy.toml .
uv run ty check --project . --config-file linters/ty.toml
```

## Releasing

To release a new version, run the interactive script (it requires the [`gh`](https://cli.github.com/) CLI,
authenticated against the repository):

```shell
uv run scripts/release.py
```
