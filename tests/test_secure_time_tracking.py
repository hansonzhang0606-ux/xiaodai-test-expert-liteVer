import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/xiaodai-lite-orchestrator/scripts/secure_record_time_saved.py"


def load_module():
    spec = importlib.util.spec_from_file_location("secure_record_time_saved", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SecureTimeTrackingTests(unittest.TestCase):
    def test_authorization_requires_exact_active_name_and_business_line(self):
        module = load_module()
        roster = {
            "status": "ok",
            "members": [
                {
                    "name": "测试用户",
                    "biz_line": ["效贷"],
                    "biz_line_code": ["XD"],
                    "active": True,
                },
                {
                    "name": "停用用户",
                    "biz_line": ["效贷"],
                    "biz_line_code": ["XD"],
                    "active": False,
                },
            ],
        }
        self.assertTrue(module.authorize_employee(roster, "测试用户", "效贷"))
        self.assertTrue(module.authorize_employee(roster, " 测试用户 ", "效贷"))
        self.assertFalse(module.authorize_employee(roster, "测试", "效贷"))
        self.assertFalse(module.authorize_employee(roster, "测试用户", "效融"))
        self.assertFalse(module.authorize_employee(roster, "停用用户", "效贷"))

    def test_authorization_fails_closed_when_roster_is_unavailable(self):
        module = load_module()
        self.assertFalse(module.authorize_employee({"status": "error"}, "测试用户", "效贷"))
        self.assertFalse(module.authorize_employee({}, "测试用户", "效贷"))

    def test_all_host_prompts_route_records_through_secure_wrapper(self):
        hooks = (
            ROOT / "skills/xiaodai-lite-orchestrator/prompts/time_tracking_hooks.md"
        ).read_text(encoding="utf-8")
        agent = (
            ROOT / "xiaodai-testing-expert-lite/agents/xiaodai-testing-expert-lite.md"
        ).read_text(encoding="utf-8")
        self.assertIn("secure_record_time_saved.py", hooks)
        self.assertIn("secure_record_time_saved.py", agent)
        self.assertNotIn("调用 `time-tracking-skill/scripts/record_time_saved.py`", hooks)


if __name__ == "__main__":
    unittest.main()
