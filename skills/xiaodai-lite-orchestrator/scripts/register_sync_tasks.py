#!/usr/bin/env python3
"""Register the orchestrator-owned Windows time-sync tasks."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


SCHEDULES = (("早", "09:00"), ("午", "12:00"), ("晚", "18:00"))
SUPPORTED_BUSINESS_LINES = ("效贷", "效融", "小贷")


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="gbk",
        errors="replace",
        timeout=60,
        check=False,
    )


def task_exists(task_name: str) -> bool:
    return run(["schtasks", "/query", "/tn", task_name]).returncode == 0


def register_one(bat_path: Path, biz_line: str, label: str, hhmm: str) -> tuple[str, str]:
    task_name = f"{biz_line}时间同步-{label}"
    if task_exists(task_name):
        return task_name, "已存在(跳过)"
    task_action = f'"{bat_path}" "{biz_line}"'
    result = run(
        [
            "schtasks",
            "/create",
            "/tn",
            task_name,
            "/tr",
            task_action,
            "/sc",
            "daily",
            "/st",
            hhmm,
            "/f",
        ]
    )
    if result.returncode == 0:
        return task_name, f"已创建({hhmm})"
    detail = (result.stderr or result.stdout).strip().replace("\n", " ")[:160]
    return task_name, f"失败(rc={result.returncode}) {detail}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="注册轻量版节省工时定时同步任务")
    parser.add_argument("--biz-line", required=True, choices=SUPPORTED_BUSINESS_LINES)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    bat_path = Path(__file__).resolve().with_name("sync_task.bat")
    if not bat_path.is_file():
        print("[ERROR] 未找到编排器自带的 sync_task.bat。", file=sys.stderr)
        return 2

    if args.dry_run:
        for label, hhmm in SCHEDULES:
            task_name = f"{args.biz_line}时间同步-{label}"
            state = "已存在" if task_exists(task_name) else f"将创建@{hhmm}"
            print(f"[DRY] {task_name}: {state}")
        return 0

    results = [
        register_one(bat_path, args.biz_line, label, hhmm)
        for label, hhmm in SCHEDULES
    ]
    ready = 0
    for name, status in results:
        print(f"{name}: {status}")
        if status.startswith("已创建") or status.startswith("已存在"):
            ready += 1
    print(f"[SUMMARY] {ready}/{len(results)} 任务就绪")
    return 0 if ready == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
