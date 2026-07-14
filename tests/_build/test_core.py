from pgmig._build._core import _expand_query


def test_expand_query_substitutes_extension_leg_exactly() -> None:
    """
    An {{exclude_extension_owned:EXPR}} placeholder expands to the shared pg_depend
    extension-ownership NOT EXISTS leg, keyed by EXPR, preserving the leading indentation
    the placeholder sat at.
    """
    expanded = _expand_query("    {{exclude_extension_owned:t.oid}}")
    assert expanded == (
        "    AND NOT EXISTS (\n"
        "        SELECT\n"
        "            1\n"
        "        FROM\n"
        "            pg_depend d\n"
        "        WHERE\n"
        "            d.objid = t.oid\n"
        "            AND d.deptype = 'e')"
    )


def test_expand_query_substitutes_every_occurrence() -> None:
    """
    Every placeholder expands, each with its own object-oid expression.
    """
    expanded = _expand_query("{{exclude_extension_owned:n.oid}}\n    {{exclude_extension_owned:c.oid}};")
    assert "{{" not in expanded
    assert expanded.count("AND NOT EXISTS (") == 2
    assert "d.objid = n.oid" in expanded
    assert "d.objid = c.oid" in expanded
    assert expanded.endswith("'e');")


def test_expand_query_tolerates_pg_format_spacing() -> None:
    """
    pgFormatter rewrites the token to `{{exclude_extension_owned :EXPR }}` (spaces around
    the colon and before the braces); the expander must still recognize it.
    """
    expanded = _expand_query("    {{exclude_extension_owned :c.oid }}")
    assert expanded.endswith("d.objid = c.oid\n            AND d.deptype = 'e')")


def test_expand_query_without_placeholder_is_unchanged() -> None:
    """
    A query carrying no placeholder passes through untouched.
    """
    query = "SELECT 1\nFROM pg_class"
    assert _expand_query(query) == query
