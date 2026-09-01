import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


class PromptContractV59Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prompt = (SKILL_ROOT / "prompts" / "time_tracking.md").read_text(
            encoding="utf-8"
        )

    def test_uses_reference_midpoint_for_adopt_and_no_feedback(self):
        self.assertIn("(min_hours + max_hours) / 2", self.prompt)
        self.assertIn("用户未反馈，采用参考中间值", self.prompt)
        self.assertNotIn("仍拒绝则记录 `time_saved_hours=0`", self.prompt)
        self.assertNotIn('"采纳" → 使用参考时间的上限值', self.prompt)

    def test_keeps_ai_estimate_separate_from_recorded_time(self):
        self.assertIn("ai_estimated_time_saved_hours", self.prompt)
        self.assertIn("不得写入 `time_saved_hours`", self.prompt)

    def test_does_not_wait_for_third_confirmation_after_no_feedback(self):
        self.assertIn("不再等待第三次确认", self.prompt)


if __name__ == "__main__":
    unittest.main()

