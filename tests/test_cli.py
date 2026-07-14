from pathlib import Path

from pytest_mock import MockerFixture
from typer.testing import CliRunner

from pgmig._cli import app
from tests.api.generate_setup import GenerateSetup

_runner = CliRunner()


def test_generate_to_stdout(gen_setup: GenerateSetup) -> None:
    gen_setup.dst.execute("CREATE TABLE person (name text)")

    result = _runner.invoke(app, ["generate", "--source", gen_setup.src.dsn, "--target", gen_setup.dst.dsn])

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


def test_generate_unsupported_change_is_clean(gen_setup: GenerateSetup) -> None:
    # A documented limitation (UnsupportedChangeError) is a known failure: clean message,
    # no traceback and no "internal error, open an issue" prompt.
    gen_setup.src.execute("CREATE DOMAIN d AS integer")
    gen_setup.dst.execute("CREATE DOMAIN d AS text")

    result = _runner.invoke(app, ["generate", "-s", gen_setup.src.dsn, "-t", gen_setup.dst.dsn])

    assert result.exit_code == 1
    assert "not supported" in result.output
    assert "Traceback" not in result.output
    assert "internal error" not in result.output.lower()


def test_generate_check_reports_diff(gen_setup: GenerateSetup) -> None:
    # --check turns a non-empty diff into a non-zero exit (CI gate) while still showing it.
    gen_setup.dst.execute("CREATE TABLE person (name text)")

    result = _runner.invoke(app, ["generate", "-s", gen_setup.src.dsn, "-t", gen_setup.dst.dsn, "--check"])

    assert result.exit_code == 1
    assert 'CREATE TABLE "public"."person" ("name" text);' in result.output
    assert "differ" in result.output.lower()


def test_generate_check_no_diff_exits_zero(gen_setup: GenerateSetup) -> None:
    # No diff under --check is a clean pass: zero exit, nothing on stdout.
    result = _runner.invoke(app, ["generate", "-s", gen_setup.src.dsn, "-t", gen_setup.dst.dsn, "--check"])

    assert result.exit_code == 0
    assert result.stdout == ""


def test_generate_index_concurrently(gen_setup: GenerateSetup) -> None:
    # --index-concurrently emits CONCURRENTLY index statements.
    gen_setup.src.execute("CREATE TABLE person (name text)")
    gen_setup.dst.execute("CREATE TABLE person (name text)")
    gen_setup.dst.execute("CREATE INDEX person_name_idx ON person (name)")

    result = _runner.invoke(app, ["generate", "-s", gen_setup.src.dsn, "-t", gen_setup.dst.dsn, "--index-concurrently"])

    assert result.exit_code == 0
    assert result.stdout == "CREATE INDEX CONCURRENTLY person_name_idx ON public.person USING btree (name);\n"


def test_generate_dsn_from_env_vars(gen_setup: GenerateSetup) -> None:
    # With no --source/--target flags, the DSNs are read from PGMIG_SOURCE/PGMIG_TARGET.
    gen_setup.dst.execute("CREATE TABLE person (name text)")

    result = _runner.invoke(
        app, ["generate"], env={"PGMIG_SOURCE": gen_setup.src.dsn, "PGMIG_TARGET": gen_setup.dst.dsn}
    )

    assert result.exit_code == 0
    assert result.stdout == 'CREATE TABLE "public"."person" ("name" text);\n'


def test_generate_flag_overrides_env_var(gen_setup: GenerateSetup) -> None:
    # An explicit flag wins over the environment variable.
    gen_setup.dst.execute("CREATE TABLE person (name text)")

    result = _runner.invoke(
        app,
        ["generate", "--source", gen_setup.src.dsn, "--target", gen_setup.dst.dsn],
        env={"PGMIG_SOURCE": "not-a-dsn", "PGMIG_TARGET": "not-a-dsn"},
    )

    assert result.exit_code == 0
    assert result.stdout == 'CREATE TABLE "public"."person" ("name" text);\n'


def test_generate_missing_source_mentions_env_var(gen_setup: GenerateSetup) -> None:
    # No flag and no env var: the error must point at both ways of passing the DSN.
    result = _runner.invoke(app, ["generate", "--target", gen_setup.dst.dsn])

    assert result.exit_code == 2
    assert "--source" in result.output
    assert "PGMIG_SOURCE" in result.output


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


def test_ignore_extension_version_flags_pass_list(mocker: MockerFixture) -> None:
    spy = mocker.patch("pgmig._cli.generate_migration", return_value="")

    result = _runner.invoke(
        app,
        [
            "generate",
            "-s",
            "src",
            "-t",
            "tgt",
            "--ignore-extension-version",
            "postgis",
            "--ignore-extension-version",
            "hstore",
        ],
    )

    assert result.exit_code == 0
    assert spy.call_args.kwargs["ignore_extension_version"] == ["postgis", "hstore"]


def test_no_ignore_flags_passes_empty_list(mocker: MockerFixture) -> None:
    spy = mocker.patch("pgmig._cli.generate_migration", return_value="")

    result = _runner.invoke(app, ["generate", "-s", "src", "-t", "tgt"])

    assert result.exit_code == 0
    assert spy.call_args.kwargs["ignore_extension_version"] == []
