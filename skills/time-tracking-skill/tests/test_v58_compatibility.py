import hashlib
import sys
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import record_time_saved as record_module


class V58CompatibilityTests(unittest.TestCase):
    def test_step_map_is_unchanged(self):
        self.assertEqual(
            record_module.STEP_MAP,
            {
                "01": "文档整理",
                "02": "需求评审",
                "04": "生成测试点",
                "06": "用例细化",
                "07": "知识入库",
            },
        )

    def test_reference_ranges_are_unchanged(self):
        actual = {
            code: (value["min"], value["max"])
            for code, value in record_module.REFERENCE_TIMES.items()
        }
        self.assertEqual(
            actual,
            {
                "01": (2.0, 4.0),
                "02": (2.0, 3.0),
                "04": (3.0, 5.0),
                "06": (4.0, 8.0),
                "07": (1.0, 2.0),
            },
        )
        self.assertEqual(record_module.HOURS_PER_PD, 8.0)

    def test_sync_task_bat_is_byte_identical_to_v58(self):
        bat_bytes = (SCRIPTS_DIR / "sync_task.bat").read_bytes()
        digest = hashlib.sha256(bat_bytes).hexdigest()

        self.assertEqual(
            digest,
            "7c85cc662b3a3e1d6adf58cb484882a06c2cc2a01c970e36bca9774f38d4d346",
        )

    def test_distributed_roster_contains_no_members(self):
        roster = (SKILL_ROOT / "config" / "team_roster.yaml").read_text(
            encoding="utf-8"
        )

        self.assertIn("members: []", roster)


if __name__ == "__main__":
    unittest.main()

