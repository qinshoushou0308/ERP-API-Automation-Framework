import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
ERP_WORKFLOW = ROOT / ".github" / "workflows" / "erp-regression.yml"


class TestCiReportingConfig(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = yaml.load(
            ERP_WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader
        )
        cls.purchase_job = cls.workflow["jobs"]["purchase-flow"]
        cls.steps = {
            step["name"]: step
            for step in cls.purchase_job["steps"]
            if "name" in step
        }

    def require_step(self, name):
        self.assertIn(name, self.steps)
        return self.steps[name]

    def test_report_toolchain_and_history_are_reproducible(self):
        self.assertTrue(self.require_step("Set up Java")["uses"].startswith(
            "actions/setup-java@"
        ))
        self.assertTrue(self.require_step("Set up Node")["uses"].startswith(
            "actions/setup-node@"
        ))

        restore = self.require_step("Restore Allure history")
        save = self.require_step("Save Allure history")
        self.assertTrue(restore["uses"].startswith("actions/cache/restore@"))
        self.assertTrue(save["uses"].startswith("actions/cache/save@"))
        self.assertIn("erp-allure-history-", restore["with"]["restore-keys"])

        generate = self.require_step("Generate Allure report")["run"]
        self.assertIn("allure-commandline@2.43.0", generate)
        self.assertIn("report/allure-report", generate.replace("\\", "/"))

    def test_successful_report_is_published_to_github_pages(self):
        upload = self.require_step("Upload GitHub Pages artifact")
        self.assertTrue(upload["uses"].startswith(
            "actions/upload-pages-artifact@"
        ))
        self.assertEqual("report/allure-report", upload["with"]["path"])

        self.assertIn("deploy-report", self.workflow["jobs"])
        deploy_job = self.workflow["jobs"]["deploy-report"]
        self.assertEqual("purchase-flow", deploy_job["needs"])
        self.assertEqual("write", deploy_job["permissions"]["pages"])
        self.assertEqual("write", deploy_job["permissions"]["id-token"])
        deploy_step = next(
            step for step in deploy_job["steps"] if step.get("id") == "deployment"
        )
        self.assertTrue(deploy_step["uses"].startswith("actions/deploy-pages@"))

    def test_failure_creates_issue_and_keeps_job_failed(self):
        self.assertIn("permissions", self.purchase_job)
        self.assertEqual("write", self.purchase_job["permissions"].get("issues"))
        self.assertNotIn("issues", self.workflow["permissions"])

        notification = self.require_step("Create failure issue")
        self.assertIn("failure()", notification["if"])
        self.assertIn("/issues", notification["run"])
        self.assertIn("GITHUB_TOKEN", notification["env"])

        final_check = self.require_step("Keep ERP test failure status")
        self.assertIn("outcome == 'failure'", final_check["if"])

    def test_shell_scripts_do_not_expand_action_inputs_directly(self):
        for step in self.purchase_job["steps"]:
            if "run" not in step:
                continue
            self.assertNotIn("${{ inputs.", step["run"], step["name"])
            self.assertNotIn("${{ steps.", step["run"], step["name"])


if __name__ == "__main__":
    unittest.main()
