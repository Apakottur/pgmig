from pgmig._introspect._core import IntrospectionQuery
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


class PreflightQuery(IntrospectionQuery[PreflightRow, PreflightRow]):
    """
    Find out which object classes the database contains, to decide which guards and loaders to run.
    """

    file_name = "preflight.sql"
    model = PreflightRow

    def process_rows(self, rows: list[PreflightRow]) -> PreflightRow:
        return rows[0]
