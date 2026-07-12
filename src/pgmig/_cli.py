import traceback
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer

from pgmig._errors import PgmigError
from pgmig.api import generate as generate_migration

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
    help="Generate migrations between Postgres databases.",
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
    ignore_extension_version: Annotated[
        list[str] | None,
        typer.Option(
            "--ignore-extension-version",
            help="Do not emit ALTER EXTENSION ... UPDATE TO for this extension's version mismatch (repeatable).",
        ),
    ] = None,
    ignore_all_extension_versions: Annotated[
        bool,
        typer.Option(
            "--ignore-all-extension-versions",
            help="Do not emit ALTER EXTENSION ... UPDATE TO for any extension's version mismatch.",
        ),
    ] = False,
) -> None:
    """
    Generate the migration SQL that turns the source database into the target database.
    """
    # DSNs come from the flag or its environment variable; missing both is a usage error.
    source = _require_dsn(source, flag="--source", env_var="PGMIG_SOURCE")
    target = _require_dsn(target, flag="--target", env_var="PGMIG_TARGET")

    # --ignore-all-extension-versions wins over a per-extension list.
    ignore_versions: bool | list[str] = ignore_all_extension_versions or (ignore_extension_version or [])

    try:
        # Generate the migration SQL.
        sql = generate_migration(source=source, target=target, ignore_extension_version=ignore_versions)
    except PgmigError as error:
        # Known error - print message without traceback.
        typer.echo(error.message, err=True)
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

    # No diff - exit.
    if not sql:
        return

    # Write the migration SQL to stdout or a file.
    if output is None:
        typer.echo(sql)
    else:
        try:
            output.write_text(f"{sql}\n", encoding="utf-8")
        except OSError as error:
            typer.echo(f"Could not write migration output: {error}", err=True)
            raise typer.Exit(code=1) from error

    # Check mode: a non-empty diff means the source is out of date -> return non-zero exit code.
    if check:
        typer.echo("Databases differ: a migration is required.", err=True)
        raise typer.Exit(code=1)


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
