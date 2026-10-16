import contextlib
import io
import inspect
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import record_time_saved as record_module


class RecordTimeSavedV59Tests(unittest.TestCase):
    def record_to_temp_jsonl(self, **overrides):
        with tempfile.TemporaryDirectory() as temp_dir:
            records_path = Path(temp_dir) / "records.jsonl"
            kwargs = {
                "employee": "测试用户",
                "user_story": "PRJ-00884552-轻量版测试",
                "step": "文档整理",
                "step_code": "01",
                "hours": 3.0,
                "biz_line": "效贷",
                "skip_validation": True,
            }
            kwargs.update(overrides)
            with mock.patch.object(
                record_module, "get_records_path", return_value=str(records_path)
            ), mock.patch.object(record_module, "sync_to_excel_if_configured"):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                    io.StringIO()
                ):
                    result = record_module.record(**kwargs)
            saved = json.loads(records_path.read_text(encoding="utf-8").strip())
        return result, saved

    def test_records_ai_estimated_time_saved_hours(self):
        result, saved = self.record_to_temp_jsonl(
            ai_estimated_time_saved_hours=2.5
        )

        self.assertEqual(result["ai_estimated_time_saved_hours"], 2.5)
        self.assertEqual(saved["ai_estimated_time_saved_hours"], 2.5)
        self.assertEqual(saved["time_saved_hours"], 3.0)

    def test_legacy_call_records_null_ai_estimate(self):
        _, saved = self.record_to_temp_jsonl()

        self.assertIn("ai_estimated_time_saved_hours", saved)
        self.assertIsNone(saved["ai_estimated_time_saved_hours"])
        self.assertEqual(saved["time_saved_hours"], 3.0)

    def test_rejects_negative_ai_estimate(self):
        with self.assertRaises(ValueError):
            self.record_to_temp_jsonl(ai_estimated_time_saved_hours=-0.1)

    def test_rejects_non_finite_ai_estimate(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.record_to_temp_jsonl(ai_estimated_time_saved_hours=value)

    def test_rounds_ai_estimate_to_two_decimals(self):
        _, saved = self.record_to_temp_jsonl(
            ai_estimated_time_saved_hours=2.345
        )

        self.assertEqual(saved["ai_estimated_time_saved_hours"], 2.35)

    def test_new_parameter_does_not_shift_legacy_skip_validation_position(self):
        parameter_names = list(inspect.signature(record_module.record).parameters)

        self.assertEqual(
            parameter_names[-2:],
            ["skip_validation", "ai_estimated_time_saved_hours"],
        )

    def test_validation_rejects_partial_user_story(self):
        # 只给名称 / 只给编号 都应被拒绝（v6.4 用户故事完整性硬校验）
        for partial in ("【效贷0917】税票报告迭代优化V1.5", "PRJ-00884552"):
            with self.subTest(partial=partial), self.assertRaises(
                record_module.UserStoryIncompleteError
            ):
                self.record_to_temp_jsonl(user_story=partial)

    def test_validation_requires_prj_prefix(self):
        # 非 PRJ 前缀的编号不再通过校验（与提示词「形如 PRJ-00884552」一致）
        with self.assertRaises(record_module.UserStoryIncompleteError):
            self.record_to_temp_jsonl(user_story="US-001-轻量版测试")

    def test_allow_partial_user_story_bypasses_validation(self):
        _, saved = self.record_to_temp_jsonl(
            user_story="PRJ-00884552", allow_partial_user_story=True
        )

        self.assertEqual(saved["user_story"], "PRJ-00884552")


if __name__ == "__main__":
    unittest.main()
