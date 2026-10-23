# pgmig

Generate migrations between Postgres databases.

Use `pgmig` to compare the structure of two Postgres databases — a `source` and a `target` — and generate
the SQL that turns the source into the target.

`pgmig` connects **read-only** to both databases and never runs the generated SQL for you: you review it and
apply it yourself.

pgmig officially supports **Postgres 14–18** — the majors currently maintained upstream — and is tested against
each in CI. Other versions may work but are not tested.

## Installation

pgmig is available as [`pgmig`](https://pypi.org/project/pgmig/) on PyPI. Run it without installing via
[`uvx`](https://docs.astral.sh/uv/) (as in the quick start below), or install it with `uv` (recommended) or `pip`:

```shell
# With uv.
uv tool install pgmig@latest  # Install pgmig globally.
uv add --dev pgmig            # Or add pgmig to your project.

# With pip.
pip install pgmig
```

The base install uses the pure-Python psycopg driver, which needs the Postgres client library (libpq) on the machine.
For a faster build, a bundled-libpq build, or the asyncpg driver, see [which build should I install?](faq.md#which-build-should-i-install)

## Quick start

Say the `current` database has a `users` table, and the `desired` one adds an `email` column with a unique index:

```sql
-- current
CREATE TABLE users (id bigint PRIMARY KEY, name text NOT NULL);

-- desired
CREATE TABLE users (id bigint PRIMARY KEY, name text NOT NULL, email text NOT NULL);
CREATE UNIQUE INDEX users_email_idx ON users (email);
```

Print the migration SQL that makes `current` match `desired`:

```shell
$ uvx pgmig generate \
    --source postgresql://user:pass@localhost:5432/current \
    --target postgresql://user:pass@localhost:5432/desired

ALTER TABLE "public"."users" ADD COLUMN "email" text NOT NULL;
CREATE UNIQUE INDEX users_email_idx ON public.users USING btree (email);
```

Or from Python:

```python
import pgmig

sql = pgmig.generate(
    source="postgresql://user:pass@localhost:5432/current",
    target="postgresql://user:pass@localhost:5432/desired",
)

print(sql)
# ALTER TABLE "public"."users" ADD COLUMN "email" text NOT NULL;
# CREATE UNIQUE INDEX users_email_idx ON public.users USING btree (email);
```

When the two structures already match, nothing is printed and `generate` returns an empty string. From async
code, await [`agenerate`](reference/api.md#pgmig.agenerate) instead.

See [Configuration](configuration.md) for every option.
