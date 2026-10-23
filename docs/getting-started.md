# Getting Started

## Installation

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

pgmig needs the Postgres client library (libpq) on the machine; see the [FAQ](faq.md#do-i-need-libpq-installed)
to bundle it instead.

## Usage

`pgmig` can be used directly in the command line or as a Python library.

### Command line

Print the migration SQL that makes `source` match `target`:

```shell
pgmig generate \
  --source postgresql://user:pass@localhost:5432/current \
  --target postgresql://user:pass@localhost:5432/desired
```

When the two structures already match, nothing is printed.

### Library

The same diff is available as a function that returns the SQL as a string:

```python
import pgmig

sql = pgmig.generate(
    source="postgresql://user:pass@localhost:5432/current",
    target="postgresql://user:pass@localhost:5432/desired",
)

print(sql)  # the migration SQL
```

`generate` returns an empty string when the structures already match. From async code, use
[`agenerate`](reference/api.md#pgmig.agenerate) instead.
