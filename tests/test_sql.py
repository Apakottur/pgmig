from pgmig._sql import comment_on, ident, literal, qualified


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


def test_comment_on() -> None:
    assert comment_on("TABLE", '"public"."person"', "hi") == 'COMMENT ON TABLE "public"."person" IS \'hi\';'
    assert comment_on("COLUMN", '"public"."person"."id"', None) == 'COMMENT ON COLUMN "public"."person"."id" IS NULL;'
    assert comment_on("TABLE", '"public"."person"', "") == 'COMMENT ON TABLE "public"."person" IS \'\';'
    assert comment_on("TABLE", '"public"."person"', "a'b") == "COMMENT ON TABLE \"public\".\"person\" IS 'a''b';"
