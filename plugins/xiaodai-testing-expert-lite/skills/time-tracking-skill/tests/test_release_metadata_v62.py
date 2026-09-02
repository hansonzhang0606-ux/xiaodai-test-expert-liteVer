import re
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = SKILL_ROOT.parent


class ReleaseMetadataV62Tests(unittest.TestCase):
    def test_current_version_is_consistent(self):
        version = (SKILL_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        readme = (SKILL_ROOT / "README.md").read_text(encoding="utf-8")
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        prompt = (SKILL_ROOT / "prompts" / "time_tracking.md").read_text(
            encoding="utf-8"
        )
        release_notes = (PACKAGE_ROOT / "更新说明.md").read_text(encoding="utf-8")
        record_script = (SKILL_ROOT / "scripts" / "record_time_saved.py").read_text(
            encoding="utf-8"
        )
        sync_script = (SKILL_ROOT / "scripts" / "sync_to_mysql.py").read_text(
            encoding="utf-8"
        )

        self.assertEqual(version, "6.2")
        self.assertIn("v6.2", "\n".join(readme.splitlines()[:12]))
        self.assertIn("当前发布版本：**v6.2**", skill)
        self.assertIn("v6.2", prompt.splitlines()[0])
        self.assertIn("v6.2", "\n".join(release_notes.splitlines()[:10]))
        self.assertIn("v6.2", "\n".join(record_script.splitlines()[:15]))
        self.assertIn("v6.2", "\n".join(sync_script.splitlines()[:15]))

    def test_skill_frontmatter_is_discoverable(self):
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        frontmatter = skill.split("---", 2)[1]
        name_match = re.search(r"^name:\s*(.+)$", frontmatter, re.MULTILINE)
        description_match = re.search(
            r"description:\s*>-\s*\n(?P<body>(?:\s{2}.+\n?)+)",
            frontmatter,
        )

        self.assertIsNotNone(name_match)
        self.assertEqual(name_match.group(1).strip(), "time-tracking-skill")
        self.assertIsNotNone(description_match)
        description = " ".join(
            line.strip() for line in description_match.group("body").splitlines()
        )
        self.assertTrue(description.startswith("Use when"))
        self.assertLessEqual(len(description), 500)

    def test_documentation_uses_exact_new_cli_name(self):
        documents = [
            (SKILL_ROOT / "README.md").read_text(encoding="utf-8"),
            (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8"),
            (SKILL_ROOT / "prompts" / "time_tracking.md").read_text(
                encoding="utf-8"
            ),
        ]

        for document in documents:
            self.assertIn("--ai-estimated-time-saved-hours", document)

    def test_release_examples_do_not_expose_known_person_names(self):
        text_files = [
            path
            for path in SKILL_ROOT.rglob("*")
            if path.is_file() and path.suffix.lower() in {".md", ".py", ".yaml"}
        ]
        combined = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore") for path in text_files
        )

        self.assertNotIn("\u8a79\u60e0\u82f1", combined)
        self.assertNotIn("\u5468\u5cf0", combined)


if __name__ == "__main__":
    unittest.main()
