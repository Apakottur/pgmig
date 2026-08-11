import shutil
import sys
import textwrap
import traceback
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer

from pgmig._api import generate as generate_migration
from pgmig._drivers import DbDriver
from pgmig._errors import DbConnectionError, _PgmigError

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
    help="Generate migrations between Postgres databases.",
)

# Layout of the box that sets verbatim third-party output apart from pgmig's own message.
_BOX_INDENT = "  "
_BOX_MAX_WIDTH = 100
_BOX_UNICODE = ("╭", "╰", "─", "│")
_BOX_ASCII = ("+", "+", "-", "|")


def _format_database(label: str, error: BaseException | None, *, driver: DbDriver) -> list[str]:
    """
    One database's line in a connection report, followed by the driver's own words quoted in
    a box when it is the one that failed, so they do not read as more of pgmig's message.
    """
    if error is None:
        return [f"{_BOX_INDENT}{label} - REACHABLE"]

    # Box-drawing characters, downgraded to ASCII when the error stream cannot encode them
    # (e.g. output redirected under a legacy Windows code page), where drawing the nicer box
    # would raise on top of the error being reported.
    try:
        "".join(_BOX_UNICODE).encode(sys.stderr.encoding or "ascii")
    except UnicodeEncodeError:
        top_left, bottom_left, horizontal, vertical = _BOX_ASCII
    else:
        top_left, bottom_left, horizontal, vertical = _BOX_UNICODE

    # Leave room for the indent and the "| " prefix. Long words (a DSN, a URL) are left to
    # overflow rather than be chopped mid-token: the box has no right edge to breach.
    indent = _BOX_INDENT * 2
    width = min(shutil.get_terminal_size(fallback=(_BOX_MAX_WIDTH, 24)).columns, _BOX_MAX_WIDTH)
    body_width = width - len(indent) - 2

    body = []
    for line in str(error).splitlines():
        wrapped = textwrap.wrap(
            line,
            width=body_width,
            break_long_words=False,
            break_on_hyphens=False,
            subsequent_indent="    ",
        )
        # An empty line wraps to nothing; keep it, it is part of the driver's own layout.
        body.extend(wrapped or [""])

    header = f"{top_left}{horizontal} {driver.resolved} "
    return [
        f"{_BOX_INDENT}{label} - UNREACHABLE",
        f"{indent}{header}{horizontal * max(body_width + 2 - len(header), 0)}",
        *(f"{indent}{vertical} {line}".rstrip() for line in body),
        f"{indent}{bottom_left}{horizontal * (body_width + 1)}",
    ]


def _format_error(error: _PgmigError, *, driver: DbDriver) -> str:
    """
    Render a known error for the terminal. A failure to connect reports both databases the
    run needed, with the driver's own words quoted in a box under the one that failed.
    """
    if not isinstance(error, DbConnectionError):
        return error.message

    return "\n".join(
        [
            error.message,
            *_format_database("Source", error.source_error, driver=driver),
            *_format_database("Target", error.target_error, driver=driver),
        ]
    )


def _require_dsn(value: str | None, *, flag: str, env_var: str) -> str:
    """
    Return the DSN, failing with a usage error when neither the flag nor its
    environment variable provided one.
    """
    if value is None:
        typer.echo(f"Missing option '{flag}' (or set the {env_var} environment variable).", err=True)
        raise typer.Exit(code=2)
    return value


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(version("pgmig"))
        raise typer.Exit


def _write_to_file(text: str, output: Path) -> None:
    """
    Write text to a file.
    """
    try:
        output.write_text(text, encoding="utf-8")
    except OSError as error:
        typer.echo(f"Could not write to file: {error}", err=True)
        raise typer.Exit(code=1) from error


@app.command()
def generate(
    source: Annotated[
        str | None,
        typer.Option("--source", "-s", envvar="PGMIG_SOURCE", help="DSN of the source (current) database."),
    ] = None,
    target: Annotated[
        str | None,
        typer.Option("--target", "-t", envvar="PGMIG_TARGET", help="DSN of the target (desired) database."),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Write the migration SQL to this file instead of stdout."),
    ] = None,
    check: Annotated[
        bool,
        typer.Option(
            "--check",
            "-c",
            help="Exit with a non-zero status if the databases differ. Useful as a CI gate; "
            "the migration is still emitted so the drift is visible.",
        ),
    ] = False,
    index_concurrently: Annotated[
        bool,
        typer.Option(
            "--index-concurrently",
            help="Emit CREATE/DROP INDEX (including CREATE UNIQUE INDEX) with CONCURRENTLY, so "
            "index maintenance takes no blocking lock. These statements cannot run inside a "
            "transaction block -- apply them outside BEGIN/COMMIT.",
        ),
    ] = False,
    ignore_extension_version: Annotated[
        list[str] | None,
        typer.Option(
            "--ignore-extension-version",
            help="Do not emit ALTER EXTENSION ... UPDATE TO for this extension's version mismatch (repeatable).",
        ),
    ] = None,
    ignore_schema: Annotated[
        list[str] | None,
        typer.Option(
            "--ignore-schema",
            help="Exclude this schema from the diff entirely -- its objects and the schema "
            "create/drop are ignored (repeatable).",
        ),
    ] = None,
    include_owner: Annotated[
        bool,
        typer.Option(
            "--include-owner",
            help="Emit ALTER ... OWNER TO statements to reconcile ownership (off by default).",
        ),
    ] = False,
    include_grants: Annotated[
        bool,
        typer.Option(
            "--include-grants",
            help="Also emit named-role GRANT / REVOKE (PUBLIC grants are always diffed).",
        ),
    ] = False,
    driver: Annotated[
        DbDriver,
        typer.Option(
            "--driver",
            help="Database driver to connect with. 'auto' lets pgmig pick among the supported drivers.",
        ),
    ] = DbDriver.AUTO,
) -> None:
    """
    Generate the migration SQL that turns the source database into the target database.
    """
    # Get the DSNs.
    source = _require_dsn(source, flag="--source", env_var="PGMIG_SOURCE")
    target = _require_dsn(target, flag="--target", env_var="PGMIG_TARGET")

    # Generate the migration SQL.
    try:
        sql = generate_migration(
            source=source,
            target=target,
            index_concurrently=index_concurrently,
            ignore_extension_version=ignore_extension_version or [],
            ignore_schemas=ignore_schema or [],
            include_owner=include_owner,
            include_grants=include_grants,
            driver=driver,
        )
    except _PgmigError as error:
        # Expected error - print message without traceback.
        typer.echo(_format_error(error, driver=driver), err=True)
        raise typer.Exit(code=1) from error
    except Exception as error:
        # Internal error - print traceback and issue prompt.
        typer.echo(traceback.format_exc(), err=True)
        typer.echo(
            "This is an internal error in pgmig. Please open an issue with the traceback above:\n"
            "https://github.com/Apakottur/pgmig/issues",
            err=True,
        )
        raise typer.Exit(code=1) from error

    if sql:
        # Schemas are not in sync.

        # Write to file/stdout.
        if output:
            _write_to_file(f"{sql}\n", output)
        else:
            typer.echo(sql)

        # Exit with a non-zero status if the databases differ.
        if check:
            typer.echo("Databases differ: a migration is required.", err=True)
            raise typer.Exit(code=1)
    else:
        # Schemas are in sync.

        # Truncate the file if it exists.
        if output:
            _write_to_file("", output)


@app.callback()
def main(
    _version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show the version and exit."),
    ] = False,
) -> None:
    """
    Generate migrations between Postgres databases.
    """


if __name__ == "__main__":
    app()
