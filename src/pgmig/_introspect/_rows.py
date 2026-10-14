from pydantic import BaseModel, ConfigDict

from pgmig._models import Grant


class IntrospectionRow(BaseModel):
    """
    Base for every model parsed from a bundled SQL query -- a top-level row, or a nested
    jsonb object a query builds.
    """

    model_config = ConfigDict(
        # Ensure queries dont fetch unused columns.
        extra="forbid",
    )


class IntrospectionRowWithSchema(IntrospectionRow):
    """
    Base for every top-level row that carries a required schema in `schema_name` -- the schema an
    object belongs to. A shared base so that schema-bearing rows can be told apart from the rest
    (dependency rows carry a pair of schemas, a few carry none).
    """

    schema_name: str


class GrantRow(IntrospectionRow):
    """
    One effective privilege of an object's ACL (jsonb object built by the queries).
    """

    grantee: str
    privilege: str
    grantable: bool


def grants(rows: list[GrantRow]) -> frozenset[Grant]:
    """
    Convert parsed ACL rows into the model's grant set.
    """
    return frozenset(Grant(grantee=row.grantee, privilege=row.privilege, grantable=row.grantable) for row in rows)
