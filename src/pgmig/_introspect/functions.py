from pgmig._introspect._context import context
from pgmig._introspect._core import _QueryRow, run_introspection_query
from pgmig._models import Function, FunctionKey, RelationKey


class _FunctionDep(_QueryRow):
    """A routine another routine hard-depends on (jsonb object from functions.sql)."""

    schema_name: str
    name: str
    args: str  # pg_get_function_identity_arguments


class _RelationDep(_QueryRow):
    """A table/view/matview a routine hard-depends on (jsonb object from functions.sql)."""

    schema_name: str
    name: str


class _FunctionRow(_QueryRow):
    schema_name: str
    func_name: str
    func_args: str
    func_def: str
    func_rettype: str
    func_kind: str
    func_comment: str | None
    func_has_dependents: bool
    func_depends_on_functions: list[_FunctionDep]
    func_depends_on_relations: list[_RelationDep]


async def load() -> None:
    """
    Functions and procedures (excluding aggregates, window functions, and extension-owned ones).
    """
    for func_row in await run_introspection_query("functions.sql", _FunctionRow):
        signature = f"{func_row.func_name}({func_row.func_args})"
        context.db_info.schema_by_name[func_row.schema_name].function_by_signature[signature] = Function(
            name=func_row.func_name,
            identity_arguments=func_row.func_args,
            definition=func_row.func_def.rstrip(),
            return_type=func_row.func_rettype,
            kind=func_row.func_kind,
            comment=func_row.func_comment,
            has_dependents=func_row.func_has_dependents,
            depends_on_functions=frozenset(
                FunctionKey(schema=dep.schema_name, signature=f"{dep.name}({dep.args})")
                for dep in func_row.func_depends_on_functions
            ),
            depends_on_relations=frozenset(
                RelationKey(schema=dep.schema_name, name=dep.name) for dep in func_row.func_depends_on_relations
            ),
        )
