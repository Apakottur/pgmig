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


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(version("pgmig"))
        raise typer.Exit


@app.command()
def generate(
    source: Annotated[str, typer.Option("--source", "-s", help="DSN of the source (current) database.")],
    target: Annotated[str, typer.Option("--target", "-t", help="DSN of the target (desired) database.")],
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
) -> None:
    """
    Generate the migration SQL that turns the source database into the target database.
    """
    try:
        # Generate the migration SQL.
        sql = generate_migration(source=source, target=target)
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
