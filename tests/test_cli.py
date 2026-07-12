from pathlib import Path

from typer.testing import CliRunner

from pgmig._cli import app
from tests.fixtures.generate_setup import GenerateSetup

runner = CliRunner()

_EXPECTED = 'CREATE TABLE "public"."person" ("name" text);\n'


def test_generate_to_stdout(gen_setup: GenerateSetup) -> None:
    gen_setup.dst.execute("CREATE TABLE person (name text)")

    result = runner.invoke(app, ["generate", "--source", gen_setup.src.dsn, "--target", gen_setup.dst.dsn])

    assert result.exit_code == 0
    assert result.stdout == _EXPECTED


def test_generate_short_flags(gen_setup: GenerateSetup) -> None:
    gen_setup.dst.execute("CREATE TABLE person (name text)")

    result = runner.invoke(app, ["generate", "-s", gen_setup.src.dsn, "-t", gen_setup.dst.dsn])

    assert result.exit_code == 0
    assert result.stdout == _EXPECTED


def test_generate_to_file(gen_setup: GenerateSetup, tmp_path: Path) -> None:
    gen_setup.dst.execute("CREATE TABLE person (name text)")
    out = tmp_path / "migration.sql"

    result = runner.invoke(app, ["generate", "-s", gen_setup.src.dsn, "-t", gen_setup.dst.dsn, "-o", str(out)])

    assert result.exit_code == 0
    assert result.stdout == ""
    assert out.read_text() == _EXPECTED


def test_generate_empty_diff_no_output(gen_setup: GenerateSetup) -> None:
    result = runner.invoke(app, ["generate", "-s", gen_setup.src.dsn, "-t", gen_setup.dst.dsn])

    assert result.exit_code == 0
    assert result.stdout == ""


def test_generate_missing_target_exits_2() -> None:
    result = runner.invoke(app, ["generate", "-s", "postgresql://x"])

    assert result.exit_code == 2


def test_generate_bad_dsn_errors() -> None:
    result = runner.invoke(app, ["generate", "-s", "not-a-dsn", "-t", "not-a-dsn"])

    assert result.exit_code == 1
    assert "Error" in result.output


def test_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() != ""
