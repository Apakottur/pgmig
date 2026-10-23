<p align="center">
  <img src="https://github.com/Apakottur/pgmig/blob/main/pgmig.png?raw=true" width="400" />
</p>

[![image](https://img.shields.io/pypi/v/pgmig.svg)](https://pypi.python.org/pypi/pgmig)
[![image](https://img.shields.io/pypi/l/pgmig.svg)](https://github.com/Apakottur/pgmig/blob/main/LICENSE)
[![image](https://img.shields.io/pypi/pyversions/pgmig.svg)](https://pypi.python.org/pypi/pgmig)
[![Documentation](https://readthedocs.org/projects/pgmig/badge/?version=latest)](https://pgmig.readthedocs.io/)

Generate migrations between Postgres databases.

Use `pgmig` to compare the structure of two Postgres databases — a `source` and a `target` — and generate
the SQL that turns the source into the target.

`pgmig` connects **read-only** to both databases and never
runs the generated SQL for you: you review it and apply it yourself.

pgmig officially supports **Postgres 14–18** — the majors currently maintained upstream — and is
tested against each in CI. Other versions may work but are not tested.

This project is currently in active development, see [Roadmap](https://github.com/Apakottur/pgmig/issues/8).

**Documentation**: [pgmig.readthedocs.io](https://pgmig.readthedocs.io/)

## Quick start

Print the migration SQL that makes `source` match `target`, using [`uvx`](https://docs.astral.sh/uv/):

```shell
uvx pgmig generate \
  --source postgresql://user:pass@localhost:5432/current \
  --target postgresql://user:pass@localhost:5432/desired
```

Or from Python:

```python
import pgmig

sql = pgmig.generate(
    source="postgresql://user:pass@localhost:5432/current",
    target="postgresql://user:pass@localhost:5432/desired",
)
```

See the [documentation](https://pgmig.readthedocs.io/) for installation, every option, and the Python API.

## Contributing

Contributions are welcome!

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

`pgmig` is distributed under the terms of the [MIT license](LICENSE).
