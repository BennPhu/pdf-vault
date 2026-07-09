"""Enforce the Power of 10 rules (NASA/JPL, adapted for Python) via AST checks.

Rules covered here:
- Rule 1: no recursion (direct self-calls)
- Rule 2: no unbounded `while True` loops
- Rule 4: no function longer than 60 lines
- Rule 8 (adapted): no eval/exec/compile in application code
"""

import ast
from pathlib import Path

import pytest

APP_MODULES = ["pdf_core.py", "api.py", "app.py", "updater.py"]
MAX_FUNCTION_LINES = 60
BASE = Path(__file__).resolve().parent.parent


def _functions(module):
    tree = ast.parse((BASE / module).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


@pytest.mark.parametrize("module", APP_MODULES)
def test_no_function_longer_than_60_lines(module):
    violations = [
        f"{module}:{fn.lineno} {fn.name} ({fn.end_lineno - fn.lineno + 1} lines)"
        for fn in _functions(module)
        if fn.end_lineno - fn.lineno + 1 > MAX_FUNCTION_LINES
    ]
    assert not violations, f"Functions exceed {MAX_FUNCTION_LINES} lines: {violations}"


@pytest.mark.parametrize("module", APP_MODULES)
def test_no_direct_recursion(module):
    violations = []
    for fn in _functions(module):
        for node in ast.walk(fn):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == fn.name):
                violations.append(f"{module}:{node.lineno} {fn.name} calls itself")
    assert not violations, f"Recursion found: {violations}"


@pytest.mark.parametrize("module", APP_MODULES)
def test_no_unbounded_while_loops(module):
    tree = ast.parse((BASE / module).read_text(encoding="utf-8"))
    violations = [
        f"{module}:{node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.While)
        and isinstance(node.test, ast.Constant) and node.test.value is True
    ]
    assert not violations, f"Unbounded 'while True' loops: {violations}"


@pytest.mark.parametrize("module", APP_MODULES)
def test_no_dynamic_code_execution(module):
    tree = ast.parse((BASE / module).read_text(encoding="utf-8"))
    banned = {"eval", "exec", "compile", "__import__"}
    violations = [
        f"{module}:{node.lineno} {node.func.id}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name) and node.func.id in banned
    ]
    assert not violations, f"Dynamic code execution found: {violations}"
