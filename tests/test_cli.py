import asyncio
import os
from pathlib import Path
from types import SimpleNamespace

from pytest_mock import MockerFixture
from typer.testing import CliRunner, Result

from pgmig._cli._cli import app
from tests._api.generate_setup import GenerateSetup

_runner = CliRunner()


async def _run_cli(args: str, env: dict[str, str] | None = None) -> Result:
    """
    Run the CLI application.
    """
    # We need to wrap with asyncio.to_thread to prevent an issue with asyncio event loops and typer.
    return await asyncio.to_thread(lambda: _runner.invoke(app, args, env=env))


async def test_generate_to_stdout(gen_setup: GenerateSetup) -> None:
    await gen_setup.dst.execute("CREATE TABLE person (name text)")

    result = await _run_cli(f"generate --source {gen_setup.src.dsn} --target {gen_setup.dst.dsn}")

    assert result.exit_code == 0
    assert result.stdout == 'CREATE TABLE "public"."person" ("name" text);\n'


async def test_generate_to_file(gen_setup: GenerateSetup, tmp_path: Path) -> None:
    await gen_setup.dst.execute("CREATE TABLE person (name text)")
    out = tmp_path / "migration.sql"

    result = await _run_cli(f"generate -s {gen_setup.src.dsn} -t {gen_setup.dst.dsn} -o {out!s}")

    assert result.exit_code == 0
    assert result.stdout == ""
    assert out.read_text() == 'CREATE TABLE "public"."person" ("name" text);\n'


async def test_generate_empty_diff_no_output(gen_setup: GenerateSetup) -> None:
    result = await _run_cli(f"generate -s {gen_setup.src.dsn} -t {gen_setup.dst.dsn}")

    assert result.exit_code == 0
    assert result.stdout == ""


async def test_generate_empty_diff_truncates_stale_output(gen_setup: GenerateSetup, tmp_path: Path) -> None:
    # An empty diff must overwrite the --output file so it reflects the current run, not
    # leave a stale migration from a previous run on disk.
    out = tmp_path / "migration.sql"
    out.write_text("CREATE TABLE stale (x int);\n", encoding="utf-8")

    result = await _run_cli(f"generate -s {gen_setup.src.dsn} -t {gen_setup.dst.dsn} -o {out!s}")

    assert result.exit_code == 0
    assert out.read_text() == ""


async def test_generate_connection_error_is_clean() -> None:
    # A bad connection string is an expected failure: clean message, no traceback, and the
    # driver's own text quoted in a box below it rather than run into pgmig's message.
    result = await _run_cli("generate -s not-a-dsn -t not-a-dsn")

    assert result.exit_code == 1
    assert "Failed to connect to one of the databases:" in result.output
    assert "Source - UNREACHABLE" in result.output
    assert "Target - UNREACHABLE" in result.output
    assert "╭─ psycopg " in result.output
    assert "│ Invalid connection string." in result.output
    assert "Traceback" not in result.output


async def test_generate_reports_the_reachable_side_too(gen_setup: GenerateSetup) -> None:
    # Which side is the problem is the first thing to know, so a working database is
    # listed as reachable rather than left out of the report.
    result = await _run_cli(f"generate -s {gen_setup.src.dsn} -t postgresql://pgmig:pgmig@localhost:15432/nope")

    assert result.exit_code == 1
    assert "Source - REACHABLE" in result.output
    assert "Target - UNREACHABLE" in result.output
    assert 'database "nope" does not exist' in result.output


async def test_generate_reports_an_unreachable_source(gen_setup: GenerateSetup) -> None:
    # The mirror image: each side is reported on whichever one of them failed.
    result = await _run_cli(f"generate -s postgresql://pgmig:pgmig@localhost:15432/nope -t {gen_setup.dst.dsn}")

    assert result.exit_code == 1
    assert "Source - UNREACHABLE" in result.output
    assert "Target - REACHABLE" in result.output


async def test_generate_does_not_echo_an_unparsable_connection_string() -> None:
    # A connection string that fails URI parsing is reported by libpq with the string
    # quoted back, password and all, so that message is dropped rather than passed on.
    result = await _run_cli("generate -s user:swordfish@localhost:5432/db -t user:swordfish@localhost:5432/db")

    assert result.exit_code == 1
    assert "swordfish" not in result.output
    assert "localhost" not in result.output
    assert "Invalid connection string." in result.output


async def test_generate_wraps_the_driver_error_to_the_terminal_width(mocker: MockerFixture) -> None:
    # The driver's text is quoted verbatim, wrapped to fit, with continuation lines indented
    # so a wrapped line cannot be mistaken for a new one.
    mocker.patch("pgmig._cli._error_format.shutil.get_terminal_size", return_value=os.terminal_size((60, 24)))

    result = await _run_cli("generate -s not-a-dsn -t not-a-dsn")

    assert result.exit_code == 1
    assert "  Source - UNREACHABLE" in result.output
    assert "    ╭─ psycopg ─────────────────────────────────────────────" in result.output
    assert "    │ Invalid connection string. The driver's own message is" in result.output
    assert "    │     not shown here because it quotes the connection" in result.output
    assert "    ╰───────────────────────────────────────────────────────" in result.output


async def test_generate_falls_back_to_an_ascii_box_when_stderr_cannot_encode(mocker: MockerFixture) -> None:
    # Output redirected under a legacy code page: drawing the nicer box would raise. The
    # module's own `sys` is replaced rather than sys.stderr, which the CLI runner rebinds to
    # its capture buffer once the command is running.
    mocker.patch("pgmig._cli._error_format.sys", SimpleNamespace(stderr=SimpleNamespace(encoding="ascii")))

    result = await _run_cli("generate -s not-a-dsn -t not-a-dsn")

    assert result.exit_code == 1
    assert "+- psycopg " in result.output
    assert "| Invalid connection string." in result.output
    assert "╭" not in result.output


async def test_generate_internal_error_reports_issue(mocker: MockerFixture) -> None:
    # An unexpected failure is an internal error: full traceback plus an issue prompt.
    mocker.patch("pgmig._cli._cli.generate_migration", side_effect=ValueError("boom"))

    result = await _run_cli("generate -s src -t tgt")

    assert result.exit_code == 1
    assert "internal error" in result.output.lower()
    assert "github.com/Apakottur/pgmig/issues" in result.output
    assert "ValueError" in result.output


async def test_generate_unsupported_change_is_clean(gen_setup: GenerateSetup) -> None:
    # A documented limitation (UnsupportedChangeError) is a known failure: clean message,
    # no traceback and no "internal error, open an issue" prompt.
    await gen_setup.src.execute("CREATE DOMAIN d AS integer")
    await gen_setup.dst.execute("CREATE DOMAIN d AS text")

    result = await _run_cli(f"generate -s {gen_setup.src.dsn} -t {gen_setup.dst.dsn}")

    assert result.exit_code == 1
    assert "not supported" in result.output
    assert "Traceback" not in result.output
    assert "internal error" not in result.output.lower()


async def test_generate_check_reports_diff(gen_setup: GenerateSetup) -> None:
    # --check turns a non-empty diff into a non-zero exit (CI gate) while still showing it.
    await gen_setup.dst.execute("CREATE TABLE person (name text)")

    result = await _run_cli(f"generate -s {gen_setup.src.dsn} -t {gen_setup.dst.dsn} --check")

    assert result.exit_code == 1
    assert 'CREATE TABLE "public"."person" ("name" text);' in result.output
    assert "differ" in result.output.lower()


async def test_generate_index_concurrently(gen_setup: GenerateSetup) -> None:
    # --index-concurrently emits CONCURRENTLY index statements.
    await gen_setup.src.execute("CREATE TABLE person (name text)")
    await gen_setup.dst.execute("CREATE TABLE person (name text)")
    await gen_setup.dst.execute("CREATE INDEX person_name_idx ON person (name)")

    result = await _run_cli(f"generate -s {gen_setup.src.dsn} -t {gen_setup.dst.dsn} --index-concurrently")

    assert result.exit_code == 0
    assert result.stdout == "CREATE INDEX CONCURRENTLY person_name_idx ON public.person USING btree (name);\n"


async def test_generate_dsn_from_env_vars(gen_setup: GenerateSetup) -> None:
    # With no --source/--target flags, the DSNs are read from PGMIG_SOURCE/PGMIG_TARGET.
    await gen_setup.dst.execute("CREATE TABLE person (name text)")

    result = await _run_cli("generate", env={"PGMIG_SOURCE": gen_setup.src.dsn, "PGMIG_TARGET": gen_setup.dst.dsn})

    assert result.exit_code == 0
    assert result.stdout == 'CREATE TABLE "public"."person" ("name" text);\n'


async def test_generate_flag_overrides_env_var(gen_setup: GenerateSetup) -> None:
    # An explicit flag wins over the environment variable.
    await gen_setup.dst.execute("CREATE TABLE person (name text)")

    result = await _run_cli(
        f"generate --source {gen_setup.src.dsn} --target {gen_setup.dst.dsn}",
        env={"PGMIG_SOURCE": "not-a-dsn", "PGMIG_TARGET": "not-a-dsn"},
    )

    assert result.exit_code == 0
    assert result.stdout == 'CREATE TABLE "public"."person" ("name" text);\n'


async def test_generate_missing_source_mentions_env_var(gen_setup: GenerateSetup) -> None:
    # No flag and no env var: the error must point at both ways of passing the DSN.
    result = await _run_cli(f"generate --target {gen_setup.dst.dsn}")

    assert result.exit_code == 2
    assert "--source" in result.output
    assert "PGMIG_SOURCE" in result.output


async def test_version() -> None:
    result = await _run_cli("--version")

    assert result.exit_code == 0
    assert result.stdout.strip() != ""


async def test_generate_unwritable_output_is_clean(gen_setup: GenerateSetup, tmp_path: Path) -> None:
    # --output pointing into a nonexistent directory is a clean write failure, not a traceback.
    await gen_setup.dst.execute("CREATE TABLE person (name text)")
    out = tmp_path / "nope" / "migration.sql"

    result = await _run_cli(f"generate -s {gen_setup.src.dsn} -t {gen_setup.dst.dsn} -o {out!s}")

    assert result.exit_code == 1
    assert "Could not write to file" in result.output
    assert "Traceback" not in result.output


async def test_ignore_extension_version_flags_pass_list(mocker: MockerFixture) -> None:
    spy = mocker.patch("pgmig._cli._cli.generate_migration", return_value="")

    result = await _run_cli(
        "generate -s src -t tgt --ignore-extension-version postgis --ignore-extension-version hstore"
    )

    assert result.exit_code == 0
    assert spy.call_args.kwargs["ignore_extension_version"] == ["postgis", "hstore"]


async def test_ignore_schema_flags_pass_list(mocker: MockerFixture) -> None:
    spy = mocker.patch("pgmig._cli._cli.generate_migration", return_value="")

    result = await _run_cli("generate -s src -t tgt --ignore-schema audit --ignore-schema staging")

    assert result.exit_code == 0
    assert spy.call_args.kwargs["ignore_schemas"] == ["audit", "staging"]
