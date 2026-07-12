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
) -> None:
    """
    Generate the migration SQL that turns the source database into the target database.
    """
    try:
        sql = generate_migration(source=source, target=target)

        if not sql:
            return

        if output is not None:
            output.write_text(f"{sql}\n", encoding="utf-8")
        else:
            typer.echo(sql)
    except PgmigError as error:
        typer.echo(error.message, err=True)
        raise typer.Exit(code=1) from error
    except OSError as error:
        # e.g. --output points at an unwritable path; report cleanly, not as a traceback.
        typer.echo(f"Could not write migration output: {error}", err=True)
        raise typer.Exit(code=1) from error
    except Exception as error:
        typer.echo(traceback.format_exc(), err=True)
        typer.echo(
            "This is an internal error in pgmig. Please open an issue with the traceback above:\n"
            "https://github.com/Apakottur/pgmig/issues",
            err=True,
        )
        raise typer.Exit(code=1) from error


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
