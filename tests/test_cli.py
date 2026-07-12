from pathlib import Path

from pytest_mock import MockerFixture
from typer.testing import CliRunner

from pgmig._cli import app
from tests.fixtures.generate_setup import GenerateSetup

_runner = CliRunner()


def test_generate_to_stdout(gen_setup: GenerateSetup) -> None:
    gen_setup.dst.execute("CREATE TABLE person (name text)")

    result = _runner.invoke(app, ["generate", "--source", gen_setup.src.dsn, "--target", gen_setup.dst.dsn])

    assert result.exit_code == 0
    assert result.stdout == 'CREATE TABLE "public"."person" ("name" text);\n'


def test_generate_short_flags(gen_setup: GenerateSetup) -> None:
    gen_setup.dst.execute("CREATE TABLE person (name text)")

    result = _runner.invoke(app, ["generate", "-s", gen_setup.src.dsn, "-t", gen_setup.dst.dsn])

    assert result.exit_code == 0
    assert result.stdout == 'CREATE TABLE "public"."person" ("name" text);\n'


def test_generate_to_file(gen_setup: GenerateSetup, tmp_path: Path) -> None:
    gen_setup.dst.execute("CREATE TABLE person (name text)")
    out = tmp_path / "migration.sql"

    result = _runner.invoke(app, ["generate", "-s", gen_setup.src.dsn, "-t", gen_setup.dst.dsn, "-o", str(out)])

    assert result.exit_code == 0
    assert result.stdout == ""
    assert out.read_text() == 'CREATE TABLE "public"."person" ("name" text);\n'


def test_generate_empty_diff_no_output(gen_setup: GenerateSetup) -> None:
    result = _runner.invoke(app, ["generate", "-s", gen_setup.src.dsn, "-t", gen_setup.dst.dsn])

    assert result.exit_code == 0
    assert result.stdout == ""


def test_generate_connection_error_is_clean() -> None:
    # A bad connection string is a known (PgmigError) failure: clean message, no traceback.
    result = _runner.invoke(app, ["generate", "-s", "not-a-dsn", "-t", "not-a-dsn"])

    assert result.exit_code == 1
    assert "Could not connect to database" in result.output
    assert "Traceback" not in result.output


def test_generate_internal_error_reports_issue(mocker: MockerFixture) -> None:
    # An unexpected failure is an internal error: full traceback plus an issue prompt.
    mocker.patch("pgmig._cli.generate_migration", side_effect=ValueError("boom"))

    result = _runner.invoke(app, ["generate", "-s", "src", "-t", "tgt"])

    assert result.exit_code == 1
    assert "internal error" in result.output.lower()
    assert "github.com/Apakottur/pgmig/issues" in result.output
    assert "ValueError" in result.output


def test_version() -> None:
    result = _runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() != ""


def test_generate_unwritable_output_is_clean(gen_setup: GenerateSetup, tmp_path: Path) -> None:
    # --output pointing into a nonexistent directory is a clean write failure, not a traceback.
    gen_setup.dst.execute("CREATE TABLE person (name text)")
    out = tmp_path / "nope" / "migration.sql"

    result = _runner.invoke(app, ["generate", "-s", gen_setup.src.dsn, "-t", gen_setup.dst.dsn, "-o", str(out)])

    assert result.exit_code == 1
    assert "Could not write migration output" in result.output
    assert "Traceback" not in result.output
