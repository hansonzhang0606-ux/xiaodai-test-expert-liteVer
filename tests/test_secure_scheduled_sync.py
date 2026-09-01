import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR_SCRIPTS = ROOT / "skills/xiaodai-lite-orchestrator/scripts"


class SecureScheduledSyncTests(unittest.TestCase):
    def test_orchestrator_owns_the_registered_task_entry(self):
        session = (
            ROOT / "skills/xiaodai-lite-orchestrator/prompts/session_start.md"
        ).read_text(encoding="utf-8")
        agent = (
            ROOT / "xiaodai-testing-expert-lite/agents/xiaodai-testing-expert-lite.md"
        ).read_text(encoding="utf-8")
        self.assertIn("xiaodai-lite-orchestrator/scripts/register_sync_tasks.py", session)
        self.assertIn("xiaodai-lite-orchestrator/scripts/register_sync_tasks.py", agent)
        self.assertTrue((ORCHESTRATOR_SCRIPTS / "register_sync_tasks.py").is_file())

    def test_scheduled_bat_uses_absolute_python_detection_and_crlf(self):
        path = ORCHESTRATOR_SCRIPTS / "sync_task.bat"
        raw = path.read_bytes()
        text = raw.decode("gbk")
        self.assertIn(b"\r\n", raw)
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
        self.assertIn("%~dp0", text)
        self.assertIn("%ProgramData%\\miniconda3\\python.exe", text)
        self.assertIn("where python.exe", text)
        self.assertNotIn('set "PY_CMD=python"', text)
        self.assertIn("time-tracking-skill", text)


if __name__ == "__main__":
    unittest.main()
