from pathlib import Path

import pgmig._introspect._core as introspect_core

_QUERIES_DIR = Path(introspect_core.__file__).parent / "queries"


def _executable_lines(query_file: str) -> list[str]:
    """
    The lines of a bundled query that Postgres actually runs: everything but the `--` comment
    lines. Comments may legitimately differ between the two view queries (they name their own
    object kind), so only the executable SQL is compared.
    """
    text = (_QUERIES_DIR / query_file).read_text(encoding="utf-8")
    return [line for line in text.splitlines() if not line.lstrip().startswith("--")]


def test_view_and_materialized_view_queries_match_except_relkind() -> None:
    """
    views.sql and materialized_views.sql must stay in lock-step: their only executable
    difference is the relkind selector ('v' for views, 'm' for matviews). This is what lets
    both loaders share views._load_views. Editing one query's body without the other silently
    changes what one kind sees, so enforce the equivalence here rather than trusting a comment.
    """
    views = [line.replace("c.relkind = 'v'", "c.relkind = 'm'") for line in _executable_lines("views.sql")]
    matviews = _executable_lines("materialized_views.sql")
    assert views == matviews
