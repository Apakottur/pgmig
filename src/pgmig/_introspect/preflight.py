from pgmig._introspect._rows import IntrospectionRow


class PreflightRow(IntrospectionRow):
    """
    Results of the introspection preflight query.
    """

    has_tables: bool
    has_views: bool
    has_matviews: bool
    has_indexes: bool
    has_constraints: bool
    has_sequences: bool
    has_functions: bool
    has_triggers: bool
    has_policies: bool
    has_enums: bool
    has_domains: bool
    has_composite_types: bool
    has_range_types: bool


def load_rows(rows: list[PreflightRow]) -> PreflightRow:
    """
    Preflight (the single row of the preflight query).
    """
    return rows[0]
