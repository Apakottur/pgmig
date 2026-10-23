# pgmig

Generate migrations between Postgres databases.

Use `pgmig` to compare the structure of two Postgres databases — a `source` and a `target` — and generate
the SQL that turns the source into the target.

`pgmig` connects **read-only** to both databases and never runs the generated SQL for you: you review it and
apply it yourself.

pgmig officially supports **Postgres 14–18** — the majors currently maintained upstream — and is tested against
each in CI. Other versions may work but are not tested.

This project is currently in active development, see [Roadmap](https://github.com/Apakottur/pgmig/issues/8).

## Quick start

```shell
uvx pgmig generate \
  --source postgresql://user:pass@localhost:5432/current \
  --target postgresql://user:pass@localhost:5432/desired
```

Continue with [Getting Started](getting-started.md) for installation and library usage, or see
[Configuration](configuration.md) for every option.
