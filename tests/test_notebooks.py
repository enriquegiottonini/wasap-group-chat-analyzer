"""Las celdas SQL de marimo se guardan como f-strings al editarlas en el navegador.

Si el SQL trae `\\` o llaves que no sean interpolaciones `{nombre}`, al guardar el notebook
queda con celdas que no compilan (y `make nbs` falla). Esta prueba lo detecta antes.
"""

import ast
from pathlib import Path
import re

import pytest

NOTEBOOKS = sorted((Path(__file__).parent.parent / "notebooks").glob("*.py"))
PLACEHOLDER = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")


def sql_literals(path: Path):
    source = path.read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        func = node.func if isinstance(node, ast.Call) else None
        is_mo_sql = (
            isinstance(func, ast.Attribute)
            and func.attr == "sql"
            and isinstance(func.value, ast.Name)
            and func.value.id == "mo"
        )
        if is_mo_sql and node.args:
            yield node.lineno, ast.get_source_segment(source, node.args[0])


@pytest.mark.parametrize("notebook", NOTEBOOKS, ids=lambda path: path.name)
def test_sql_cells_survive_marimo_f_string_round_trip(notebook):
    for lineno, literal in sql_literals(notebook):
        body = literal[literal.index('"""') + 3 : literal.rindex('"""')]
        assert literal.startswith('f"""'), f"{notebook.name}:{lineno} SQL should be an f-string"
        assert "\\" not in body, f"{notebook.name}:{lineno} SQL has a backslash"
        stray = PLACEHOLDER.sub("", body)
        assert "{" not in stray and "}" not in stray, f"{notebook.name}:{lineno} stray brace"
