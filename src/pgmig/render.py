from pgmig.diff import Change


def render(changes: list[Change]) -> str:
    # No Change variants are rendered yet; later specs emit real SQL.
    _ = changes
    return ""
