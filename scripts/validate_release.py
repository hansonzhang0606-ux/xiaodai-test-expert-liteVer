#!/usr/bin/env python3
"""Run release checks for the three-host lightweight expert package."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(label: str, command: list[str], cwd: Path = ROOT) -> None:
    print(f"[RUN] {label}")
    result = subprocess.run(command, cwd=cwd, text=True)
    if result.returncode:
        raise SystemExit(result.returncode)


def validate_bat() -> None:
    paths = [
        ROOT / "skills/xiaodai-lite-orchestrator/scripts/sync_task.bat",
        ROOT / "xiaodai-testing-expert-lite/skills/xiaodai-lite-orchestrator/scripts/sync_task.bat",
        ROOT / "plugins/xiaodai-testing-expert-lite/skills/xiaodai-lite-orchestrator/scripts/sync_task.bat",
    ]
    for path in paths:
        raw = path.read_bytes()
        raw.decode("gbk")
        if b"\r\n" not in raw or b"\n" in raw.replace(b"\r\n", b""):
            raise SystemExit(f"BAT 不是完整 CRLF：{path}")
        text = raw.decode("gbk")
        for marker in ("%~dp0", "PYTHONIOENCODING", "%~1", "where python.exe"):
            if marker not in text:
                raise SystemExit(f"BAT 缺少 {marker}：{path}")
        if "set \"PY_CMD=python\"" in text:
            raise SystemExit(f"BAT 使用了不稳定的相对 Python 命令：{path}")


def validate_manifest() -> None:
    data = json.loads((ROOT / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    if not data.get("files"):
        raise SystemExit("SOURCE_MANIFEST.json 为空")
    private_names = {"mysql_config.json", "records.jsonl"}
    for path in ROOT.rglob("*"):
        if path.is_file() and path.name in private_names:
            raise SystemExit(f"发现本机私有文件：{path}")


def main() -> int:
    run("构建发布包", [sys.executable, "scripts/build_release.py"])
    run("版本同步", [sys.executable, "scripts/check_version_sync.py"])
    run("仓库契约", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    run(
        "时间追踪 v5.9 回归",
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        ROOT / "skills/time-tracking-skill",
    )
    python_files = [
        str(path)
        for path in ROOT.joinpath("skills").rglob("*.py")
        if "pymysql" not in path.parts and "tests" not in path.parts
    ]
    run("Python 编译检查", [sys.executable, "-m", "py_compile", *python_files])
    validate_bat()
    validate_manifest()
    print("[OK] 三端发布校验全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
