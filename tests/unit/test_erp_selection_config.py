import ast
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
ERP_TEST_FILE = ROOT / "erp_tests" / "test_purchase_order.py"
PYTEST_CONFIG = ROOT / "pytest.ini"
ERP_WORKFLOW = ROOT / ".github" / "workflows" / "erp-regression.yml"


def get_pytest_markers(decorators):
    markers = set()
    for decorator in decorators:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if not isinstance(target, ast.Attribute):
            continue
        owner = target.value
        if (
            isinstance(owner, ast.Attribute)
            and isinstance(owner.value, ast.Name)
            and owner.value.id == "pytest"
            and owner.attr == "mark"
        ):
            markers.add(target.attr)
    return markers


class TestErpSelectionConfig(unittest.TestCase):
    def test_erp_tests_have_business_and_priority_markers(self):
        tree = ast.parse(ERP_TEST_FILE.read_text(encoding="utf-8"))
        test_class = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "TestPurchaseOrder"
        )

        self.assertIn("erp", get_pytest_markers(test_class.decorator_list))

        expected_markers = {
            "test_erp_login": {"smoke", "p0"},
            "test_query_completed_purchase_order": {"smoke", "p1"},
            "test_purchase_order_lifecycle": {"regression", "p0"},
            "test_purchase_receipt_increases_stock": {
                "regression",
                "inventory",
                "p0",
            },
            "test_purchase_order_rejects_invalid_operations": {
                "regression",
                "negative",
                "p1",
            },
        }
        functions = {
            node.name: node
            for node in test_class.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        for function_name, expected in expected_markers.items():
            actual = get_pytest_markers(functions[function_name].decorator_list)
            self.assertTrue(expected.issubset(actual), function_name)

    def test_pytest_registers_all_erp_markers(self):
        config = PYTEST_CONFIG.read_text(encoding="utf-8")
        for marker in (
            "erp",
            "smoke",
            "regression",
            "negative",
            "inventory",
            "p0",
            "p1",
            "p2",
        ):
            self.assertIn(f"    {marker}:", config)

    def test_erp_workflow_supports_test_suite_selection(self):
        workflow = yaml.load(
            ERP_WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader
        )
        dispatch = workflow["on"]["workflow_dispatch"]
        self.assertIsInstance(dispatch, dict)
        suite = dispatch["inputs"]["suite"]
        self.assertEqual(
            ["all", "smoke", "regression", "negative", "inventory"],
            suite["options"],
        )

        steps = workflow["jobs"]["purchase-flow"]["steps"]
        run_steps = {step["name"]: step for step in steps if "run" in step}
        self.assertIn("Run all ERP tests", run_steps)
        self.assertIn("Run selected ERP tests", run_steps)
        selected = run_steps["Run selected ERP tests"]
        self.assertIn("env", selected)
        self.assertEqual("${{ inputs.suite }}", selected["env"]["TEST_SUITE"])
        self.assertIn('-m "$env:TEST_SUITE"', selected["run"])
        self.assertNotIn("${{ inputs.suite }}", selected["run"])


if __name__ == "__main__":
    unittest.main()
