"""Static guard: every ID of the registry in framework/plan_ids.py must be referenced by at least one
@pytest.mark.plan(...) marker, and every marker must use a registered ID."""
import ast
from pathlib import Path

import pytest

from framework.plan_ids import PLAN

ROOT = Path(__file__).resolve().parents[2]


def _marker_ids():
    found = {}
    for path in (ROOT / "tests").rglob("test_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "plan"
                    and isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "mark"):
                for a in node.args:
                    if isinstance(a, ast.Constant) and isinstance(a.value, str):
                        found.setdefault(a.value, set()).add(path.name)
    return found


@pytest.mark.plan("STATIC")
def test_every_plan_id_has_at_least_one_test():
    found = _marker_ids()
    missing = sorted(set(PLAN) - set(found))
    assert not missing, f"TEST_PLAN ids without any test: {missing}"


@pytest.mark.plan("STATIC")
def test_no_marker_uses_an_unknown_plan_id():
    unknown = sorted(set(_marker_ids()) - set(PLAN))
    assert not unknown, f"markers reference ids missing from framework/plan_ids.py: {unknown}"
