from pgmig._sql import ident, literal, qualified


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
