#!/usr/bin/env python3
"""Build WorkBuddy mirrors and deterministic release archives from canonical skills."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
SKILL_NAMES = (
    "ai-testcase-workflow-skill",
    "time-tracking-skill",
    "xiaodai-lite-orchestrator",
)
EXCLUDED_DIRS = {".git", "__pycache__", ".pytest_cache", "dist"}
EXCLUDED_FILES = {"mysql_config.json", "records.jsonl"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
FIXED_ZIP_TIME = (2026, 8, 31, 0, 0, 0)


def is_excluded(path: Path) -> bool:
    return (
        any(part in EXCLUDED_DIRS for part in path.parts)
        or path.name in EXCLUDED_FILES
        or path.suffix.lower() in EXCLUDED_SUFFIXES
    )


def copy_tree(source: Path, target: Path) -> None:
    source = source.resolve()
    target = target.resolve()
    if ROOT.resolve() not in target.parents:
        raise RuntimeError(f"Refusing to write outside repository: {target}")
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "*.pyc", "*.pyo"),
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_source_manifest() -> None:
    files: dict[str, str] = {}
    for skill_name in SKILL_NAMES:
        skill_root = ROOT / "skills" / skill_name
        for path in sorted(skill_root.rglob("*")):
            if path.is_file() and not is_excluded(path.relative_to(ROOT)):
                files[path.relative_to(ROOT).as_posix()] = sha256(path)
    payload = {
        "schema_version": 1,
        "expert_version": VERSION,
        "baselines": {
            "ai-testcase-workflow-skill": "v3.7-current-working-tree",
            "time-tracking-skill": "v5.9-distribution-defaults-sanitized",
            "xiaodai-lite-orchestrator": VERSION,
        },
        "files": files,
    }
    (ROOT / "SOURCE_MANIFEST.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def zip_tree(archive_path: Path, source: Path, top_level: str, exclude_dist: bool = False) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(source)
            if is_excluded(relative) or (exclude_dist and "dist" in relative.parts):
                continue
            info = zipfile.ZipInfo(f"{top_level}/{relative.as_posix()}", FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


def main() -> int:
    package = ROOT / "xiaodai-testing-expert-lite"
    package_skills = package / "skills"
    package_skills.mkdir(parents=True, exist_ok=True)
    for skill_name in SKILL_NAMES:
        copy_tree(ROOT / "skills" / skill_name, package_skills / skill_name)
    shutil.copy2(ROOT / "skills" / "更新说明.md", package_skills / "更新说明.md")
    shutil.copy2(ROOT / "requirements.txt", package / "requirements.txt")
    avatar_source = ROOT / "assets" / "expert.png"
    if avatar_source.is_file():
        (package / "avatars").mkdir(parents=True, exist_ok=True)
        shutil.copy2(avatar_source, package / "avatars" / "expert.png")

    write_source_manifest()

    mirror = ROOT / "plugins" / "xiaodai-testing-expert-lite"
    copy_tree(package, mirror)

    dist = ROOT / "dist"
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir(parents=True)
    zip_tree(
        dist / f"xiaodai-testing-expert-lite-v{VERSION}-workbuddy.zip",
        package,
        "xiaodai-testing-expert-lite",
    )
    zip_tree(
        dist / f"xiaodai-test-expert-liteVer-v{VERSION}-source.zip",
        ROOT,
        "xiaodai-test-expert-liteVer",
        exclude_dist=True,
    )

    artifacts = []
    for path in sorted(dist.glob("*.zip")):
        artifacts.append(
            {
                "file": path.name,
                "size": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    (dist / "checksums.json").write_text(
        json.dumps({"version": VERSION, "artifacts": artifacts}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "ok", "version": VERSION, "artifacts": artifacts}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
