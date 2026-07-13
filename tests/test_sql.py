from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from pgmig._diff._context import context
from pgmig._models import DbInfo
from pgmig._sql import (
    comment_on,
    ident,
    literal,
    qualified,
    schema_qualified,
    strip_on_clause_qualifier,
    strip_routine_name_qualifier,
)


@contextmanager
def omit_schema_context(name: str | None) -> Iterator[None]:
    """
    Enter a diff context whose only relevant field is the omitted schema.
    """
    empty = DbInfo(schema_by_name={}, extension_by_name={}, view_dependencies={})
    with context.context_scope(
        source=empty, target=empty, index_concurrently=False, ignore_extension_version=(), omit_schema=name
    ):
        yield


def test_ident() -> None:
    assert ident("person") == '"person"'
    assert ident('we"ird') == '"we""ird"'
    assert ident('a"b"c') == '"a""b""c"'


def test_qualified() -> None:
    assert qualified("public") == '"public"'
    assert qualified("public", "person") == '"public"."person"'
    assert qualified("public", "person", "id") == '"public"."person"."id"'
    assert qualified("sch", 'ta"ble') == '"sch"."ta""ble"'


def test_literal() -> None:
    assert literal("hello") == "'hello'"
    assert literal("a'b") == "'a''b'"
    assert literal("a'b'c") == "'a''b''c'"
    assert literal("") == "''"


def test_schema_qualified() -> None:
    # Outside any omit context (the default), identical to qualified().
    assert schema_qualified("public", "person") == '"public"."person"'

    # Inside the context, the matching schema segment is dropped; others are kept.
    with omit_schema_context("public"):
        assert schema_qualified("public", "person") == '"person"'
        assert schema_qualified("public", "person", "id") == '"person"."id"'
        assert schema_qualified("other", "person") == '"other"."person"'

    # A None context is explicit "omit nothing".
    with omit_schema_context(None):
        assert schema_qualified("public", "person") == '"public"."person"'

    # The context resets on exit, even after an exception inside it.
    with pytest.raises(RuntimeError), omit_schema_context("public"):
        raise RuntimeError
    assert schema_qualified("public", "person") == '"public"."person"'


def test_strip_on_clause_qualifier() -> None:
    with omit_schema_context("public"):
        # Unquoted deparse form.
        assert (
            strip_on_clause_qualifier("CREATE INDEX i ON public.person USING btree (id)", "public", "person")
            == "CREATE INDEX i ON person USING btree (id)"
        )
        # Quoted deparse form (table).
        assert (
            strip_on_clause_qualifier('CREATE INDEX i ON public."Person" USING btree (id)', "public", "Person")
            == 'CREATE INDEX i ON "Person" USING btree (id)'
        )
    with omit_schema_context("Sch"):
        # Quoted deparse form (schema and table).
        assert (
            strip_on_clause_qualifier('CREATE INDEX i ON "Sch"."Person" USING btree (id)', "Sch", "Person")
            == 'CREATE INDEX i ON "Person" USING btree (id)'
        )
    # Outside any omit context: unchanged.
    assert (
        strip_on_clause_qualifier("CREATE INDEX i ON public.person USING btree (id)", "public", "person")
        == "CREATE INDEX i ON public.person USING btree (id)"
    )
    with omit_schema_context("public"):
        # Schema differing from the omitted one: unchanged.
        assert (
            strip_on_clause_qualifier("CREATE INDEX i ON other.person USING btree (id)", "other", "person")
            == "CREATE INDEX i ON other.person USING btree (id)"
        )
        # No matching form found: returned unchanged rather than mis-edited.
        assert strip_on_clause_qualifier("CREATE INDEX i ON x.y USING btree (id)", "public", "person") == (
            "CREATE INDEX i ON x.y USING btree (id)"
        )


def test_strip_routine_name_qualifier() -> None:
    with omit_schema_context("public"):
        # Function and procedure headers, unquoted deparse form.
        assert (
            strip_routine_name_qualifier("CREATE OR REPLACE FUNCTION public.bump(n integer)", "public", "bump")
            == "CREATE OR REPLACE FUNCTION bump(n integer)"
        )
        assert (
            strip_routine_name_qualifier("CREATE OR REPLACE PROCEDURE public.doit()", "public", "doit")
            == "CREATE OR REPLACE PROCEDURE doit()"
        )
        # Quoted deparse form.
        assert (
            strip_routine_name_qualifier('CREATE OR REPLACE FUNCTION public."Bump"(n integer)', "public", "Bump")
            == 'CREATE OR REPLACE FUNCTION "Bump"(n integer)'
        )
        # Schema differing from the omitted one: unchanged.
        assert (
            strip_routine_name_qualifier("CREATE OR REPLACE FUNCTION other.bump(n integer)", "other", "bump")
            == "CREATE OR REPLACE FUNCTION other.bump(n integer)"
        )
        # No matching form found: returned unchanged rather than mis-edited.
        assert (
            strip_routine_name_qualifier("CREATE OR REPLACE FUNCTION x.y(n integer)", "public", "bump")
            == "CREATE OR REPLACE FUNCTION x.y(n integer)"
        )
    # Outside any omit context: unchanged.
    assert (
        strip_routine_name_qualifier("CREATE OR REPLACE FUNCTION public.bump(n integer)", "public", "bump")
        == "CREATE OR REPLACE FUNCTION public.bump(n integer)"
    )


def test_comment_on() -> None:
    assert comment_on("TABLE", '"public"."person"', "hi") == 'COMMENT ON TABLE "public"."person" IS \'hi\';'
    assert comment_on("COLUMN", '"public"."person"."id"', None) == 'COMMENT ON COLUMN "public"."person"."id" IS NULL;'
    assert comment_on("TABLE", '"public"."person"', "") == 'COMMENT ON TABLE "public"."person" IS \'\';'
    assert comment_on("TABLE", '"public"."person"', "a'b") == "COMMENT ON TABLE \"public\".\"person\" IS 'a''b';"
