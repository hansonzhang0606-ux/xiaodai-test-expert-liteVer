#!/usr/bin/env python3
"""Check the expert version across all user-visible metadata."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    manifest = json.loads(
        (ROOT / "xiaodai-testing-expert-lite/.codebuddy-plugin/plugin.json").read_text(
            encoding="utf-8"
        )
    )
    failures = []
    if manifest.get("version") != version:
        failures.append("plugin.json version")
    if not manifest.get("displayDescription", {}).get("zh", "").startswith(f"【v{version}】"):
        failures.append("plugin.json displayDescription.zh")
    agent = (ROOT / "xiaodai-testing-expert-lite/agents/xiaodai-testing-expert-lite.md").read_text(
        encoding="utf-8"
    )
    if not re.search(rf"v{re.escape(version)}", agent):
        failures.append("WorkBuddy agent")
    readme = (ROOT / "xiaodai-testing-expert-lite/README.md").read_text(encoding="utf-8")
    if f"v{version}" not in readme:
        failures.append("WorkBuddy README")
    if failures:
        print("版本不一致：" + "、".join(failures))
        return 1
    print(f"版本一致：v{version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
