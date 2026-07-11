from pgmig.render import render


def test_no_changes_render_to_empty_sql() -> None:
    assert render([]) == ""
