import hashlib
import json
import re
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RepositoryContractTests(unittest.TestCase):
    def test_canonical_skills_exist(self):
        for name in (
            "ai-testcase-workflow-skill",
            "time-tracking-skill",
            "xiaodai-lite-orchestrator",
        ):
            self.assertTrue((ROOT / "skills" / name / "SKILL.md").is_file(), name)

    def test_runtime_dependencies_are_declared(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
        for dependency in ("openpyxl", "pyyaml", "markitdown", "pywin32"):
            self.assertIn(dependency, requirements)

    def test_orchestrator_declares_seven_stages_and_expected_tracking_map(self):
        config = (ROOT / "skills/xiaodai-lite-orchestrator/config/step_mapping.yaml").read_text(
            encoding="utf-8"
        )
        for stage in range(1, 8):
            self.assertRegex(config, rf"(?m)^\s*- id: {stage}$")
        for code in ("01", "02", "04", "06", "07"):
            self.assertRegex(config, rf'(?m)^\s+tracking_code: "{code}"$')
        self.assertEqual(config.count("tracking_code: null"), 2)

    def test_three_business_lines_are_fixed(self):
        config = (ROOT / "skills/xiaodai-lite-orchestrator/config/step_mapping.yaml").read_text(
            encoding="utf-8"
        )
        expected = {"XD": "效贷", "XR": "效融", "XXD": "小贷"}
        found = dict(re.findall(r'(?m)^\s+- code: "([A-Z]+)"\s*\n\s+name: "([^\"]+)"$', config))
        self.assertEqual(found, expected)

    def test_codex_and_vscode_discovery_entry_exists(self):
        entry = ROOT / ".agents/skills/xiaodai-testing-expert-lite/SKILL.md"
        text = entry.read_text(encoding="utf-8")
        self.assertIn("xiaodai-testing-expert-lite", text)
        self.assertIn("xiaodai-lite-orchestrator", text)

    def test_codex_skill_frontmatter_uses_supported_keys(self):
        allowed = {"name", "description", "license", "allowed-tools", "metadata"}
        skill_files = [
            ROOT / "skills/ai-testcase-workflow-skill/SKILL.md",
            ROOT / "skills/time-tracking-skill/SKILL.md",
            ROOT / "skills/xiaodai-lite-orchestrator/SKILL.md",
            ROOT / ".agents/skills/xiaodai-testing-expert-lite/SKILL.md",
        ]
        for path in skill_files:
            text = path.read_text(encoding="utf-8")
            frontmatter = text.split("---", 2)[1]
            keys = set(re.findall(r"(?m)^([a-zA-Z0-9_-]+):", frontmatter))
            self.assertTrue({"name", "description"}.issubset(keys), str(path))
            self.assertFalse(keys - allowed, f"{path}: {keys - allowed}")

    def test_new_codex_entry_descriptions_are_trigger_only(self):
        skill_files = [
            ROOT / "skills/xiaodai-lite-orchestrator/SKILL.md",
            ROOT / ".agents/skills/xiaodai-testing-expert-lite/SKILL.md",
        ]
        for path in skill_files:
            text = path.read_text(encoding="utf-8")
            frontmatter = text.split("---", 2)[1]
            self.assertRegex(frontmatter, r"(?m)^description:\s*\|\s*\n\s+Use when ")

    def test_openai_interface_metadata_is_actionable(self):
        metadata = (
            ROOT / ".agents/skills/xiaodai-testing-expert-lite/agents/openai.yaml"
        ).read_text(encoding="utf-8")
        short_match = re.search(r'(?m)^\s+short_description:\s*"([^"]+)"$', metadata)
        prompt_match = re.search(r'(?m)^\s+default_prompt:\s*"([^"]+)"$', metadata)
        self.assertIsNotNone(short_match)
        self.assertGreaterEqual(len(short_match.group(1)), 25)
        self.assertLessEqual(len(short_match.group(1)), 64)
        self.assertIsNotNone(prompt_match)
        self.assertIn("$xiaodai-testing-expert-lite", prompt_match.group(1))

    def test_workbuddy_manifest_contract(self):
        manifest = json.loads(
            (ROOT / "xiaodai-testing-expert-lite/.codebuddy-plugin/plugin.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["version"], (ROOT / "VERSION").read_text().strip())
        self.assertEqual(manifest["expertType"], "agent")
        self.assertEqual(manifest["categoryId"], "10-ProjectQuality")
        self.assertEqual(len(manifest["tags"]), 3)
        self.assertEqual(len(manifest["quickPrompts"]), 3)
        self.assertEqual(
            manifest["defaultInitPrompt"]["zh"], manifest["quickPrompts"][0]["zh"]
        )
        zh = manifest["displayDescription"]["zh"]
        self.assertTrue(zh.startswith("【v1.0.0】"))
        self.assertGreaterEqual(len(zh), 40)
        self.assertLessEqual(len(zh), 50)
        self.assertEqual(
            manifest["skills"],
            [
                "./skills/xiaodai-lite-orchestrator",
                "./skills/ai-testcase-workflow-skill",
                "./skills/time-tracking-skill",
            ],
        )
        self.assertTrue((ROOT / "xiaodai-testing-expert-lite" / manifest["avatar"]).is_file())

    def test_workbuddy_agent_frontmatter_has_no_tools(self):
        agent = (ROOT / "xiaodai-testing-expert-lite/agents/xiaodai-testing-expert-lite.md").read_text(
            encoding="utf-8"
        )
        frontmatter = agent.split("---", 2)[1]
        self.assertNotRegex(frontmatter, r"(?m)^tools:")

    def test_workbuddy_skills_are_flat(self):
        package_skills = ROOT / "xiaodai-testing-expert-lite/skills"
        for name in (
            "ai-testcase-workflow-skill",
            "time-tracking-skill",
            "xiaodai-lite-orchestrator",
        ):
            self.assertTrue((package_skills / name / "SKILL.md").is_file())
            self.assertFalse((package_skills / name / name / "SKILL.md").exists())

    def test_marketplace_points_to_plugin_mirror(self):
        marketplace = json.loads(
            (ROOT / ".codebuddy-plugin/marketplace.json").read_text(encoding="utf-8")
        )
        self.assertEqual(marketplace["plugins"][0]["source"], "./plugins/xiaodai-testing-expert-lite")

    def test_no_private_config_or_fixed_source_path(self):
        forbidden_names = {"mysql_config.json", "records.jsonl"}
        forbidden_source_root = "D:" + "\\\\##AI转型"
        forbidden_connection_defaults = (
            "172." + "20.148.36",
            "auto_efficiency_platform_" + "dev",
        )
        text_suffixes = {".md", ".json", ".yaml", ".yml", ".py", ".bat", ".txt"}
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            self.assertNotIn(path.name, forbidden_names)
            if path.suffix.lower() not in text_suffixes:
                continue
            raw = path.read_bytes()
            if path.suffix.lower() == ".bat":
                text = raw.decode("gbk")
            else:
                text = raw.decode("utf-8")
            self.assertNotIn(forbidden_source_root, text, str(path))
            for marker in forbidden_connection_defaults:
                self.assertNotIn(marker, text, str(path))
            self.assertNotRegex(text, r'"password"\s*:\s*".+"', str(path))

    def test_source_hash_manifest_matches_canonical_skills(self):
        manifest_path = ROOT / "SOURCE_MANIFEST.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for relative, expected in manifest["files"].items():
            path = ROOT / relative
            self.assertTrue(path.is_file(), relative)
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(actual, expected, relative)

    def test_release_archives_have_expected_topology(self):
        expert_zip = ROOT / "dist/xiaodai-testing-expert-lite-v1.0.0-workbuddy.zip"
        source_zip = ROOT / "dist/xiaodai-test-expert-liteVer-v1.0.0-source.zip"
        self.assertTrue(expert_zip.is_file())
        self.assertTrue(source_zip.is_file())
        with zipfile.ZipFile(expert_zip) as archive:
            names = set(archive.namelist())
            self.assertIn("xiaodai-testing-expert-lite/.codebuddy-plugin/plugin.json", names)
            self.assertIn("xiaodai-testing-expert-lite/requirements.txt", names)
            self.assertFalse(any("/.git/" in name or "__pycache__" in name for name in names))
        with zipfile.ZipFile(source_zip) as archive:
            names = set(archive.namelist())
            self.assertIn("xiaodai-test-expert-liteVer/.agents/skills/xiaodai-testing-expert-lite/SKILL.md", names)
            self.assertFalse(any("/.git/" in name or "__pycache__" in name for name in names))

    def test_release_archives_do_not_contain_private_runtime_defaults(self):
        forbidden = (
            "172." + "20.148.36",
            "auto_efficiency_platform_" + "dev",
        )
        text_suffixes = {".md", ".json", ".yaml", ".yml", ".py", ".bat", ".txt"}
        for archive_path in (
            ROOT / "dist/xiaodai-testing-expert-lite-v1.0.0-workbuddy.zip",
            ROOT / "dist/xiaodai-test-expert-liteVer-v1.0.0-source.zip",
        ):
            with zipfile.ZipFile(archive_path) as archive:
                for name in archive.namelist():
                    if Path(name).suffix.lower() not in text_suffixes:
                        continue
                    raw = archive.read(name)
                    text = raw.decode("gbk" if name.lower().endswith(".bat") else "utf-8")
                    for marker in forbidden:
                        self.assertNotIn(marker, text, f"{archive_path.name}:{name}")
                    self.assertNotRegex(
                        text,
                        r'"password"\s*:\s*".+"',
                        f"{archive_path.name}:{name}",
                    )


if __name__ == "__main__":
    unittest.main()
