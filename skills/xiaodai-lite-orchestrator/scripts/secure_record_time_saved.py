#!/usr/bin/env python3
"""Strict identity gate for time-tracking-skill v6.3 records.

This wrapper preserves the original time-tracking Skill unchanged. It fails closed
when the MySQL roster is unavailable, requires an exact active employee match for
the selected business line, and never prints roster members on authorization
failure. Only after authorization does it delegate persistence to the original
record_time_saved.py.

v6.1: 本地 records.jsonl 落盘成功后立即触发 sync_to_mysql.py 同步。
v6.3: 写盘前强制检查「编号更小」的追踪环节是否已记录（脚本级，不依赖提示词自觉）。
      存在缺失时拒绝落盘并返回退出码 2；仅在人员明确回复「跳过」后允许
      --force-with-missing 放行，并把跳过原因写入 remark 便于追溯。

退出码:
  0  成功
  2  被前序环节缺失拦截（需先补录或明确跳过）
  3  身份验证失败
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


SUPPORTED_BUSINESS_LINES = ("效贷", "效融", "小贷")
SUPPORTED_STEP_CODES = ("01", "02", "04", "06", "07")


def time_tracking_skill_root() -> Path:
    orchestrator_root = Path(__file__).resolve().parents[1]
    root = orchestrator_root.parent / "time-tracking-skill"
    if not (root / "scripts" / "load_roster.py").is_file():
        raise FileNotFoundError("time-tracking-skill is not installed beside the orchestrator")
    return root


def authorize_employee(roster: dict[str, Any], employee: str, biz_line: str) -> bool:
    """Return True only for an exact, active match in the selected business line."""
    if roster.get("status") != "ok" or not isinstance(roster.get("members"), list):
        return False
    normalized = employee.strip()
    if not normalized:
        return False
    for member in roster["members"]:
        if not isinstance(member, dict):
            continue
        if member.get("name") != normalized or member.get("active", True) is not True:
            continue
        return biz_line in member.get("biz_line", [])
    return False


def query_roster(skill_root: Path, biz_line: str) -> dict[str, Any]:
    command = [
        sys.executable,
        str(skill_root / "scripts" / "load_roster.py"),
        "--json",
        "--biz-line",
        biz_line,
    ]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    if result.returncode != 0:
        return {"status": "error"}
    try:
        payload = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        return {"status": "error"}
    return payload if isinstance(payload, dict) else {"status": "error"}


def build_record_command(args: argparse.Namespace, skill_root: Path) -> list[str]:
    command = [
        sys.executable,
        str(skill_root / "scripts" / "record_time_saved.py"),
        "--employee",
        args.employee.strip(),
        "--user-story",
        args.user_story,
        "--step",
        args.step,
        "--step-code",
        args.step_code,
        "--biz-line",
        args.biz_line,
        "--skip-validation",
    ]
    optional_values = (
        ("--hours", args.hours),
        ("--person-days", args.person_days),
        ("--remark", args.remark),
        ("--agent-start-time", args.agent_start_time),
        ("--agent-end-time", args.agent_end_time),
        ("--agent-duration-minutes", args.agent_duration_minutes),
        ("--ai-estimated-time-saved-hours", args.ai_estimated_time_saved_hours),
    )
    for flag, value in optional_values:
        if value is not None and value != "":
            command.extend((flag, str(value)))
    return command


def sync_to_mysql_after_record(biz_line: str) -> int:
    """v6.1: 写入本地记录后立即同步到 MySQL，消除定时任务时序盲区。

    同步失败不阻断本地落盘（本地 records.jsonl 是 source of truth），
    但必须明确告警，便于测试人员感知并手动重试。
    """
    try:
        skill_root = time_tracking_skill_root()
        sync_script = skill_root / "scripts" / "sync_to_mysql.py"
        if not sync_script.is_file():
            print("⚠️ 未找到 sync_to_mysql.py，跳过自动同步（本地记录已保存）。", file=sys.stderr)
            return 0
        cmd = [sys.executable, str(sync_script), "--biz-line", biz_line]
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        r = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, check=False
        )
        if r.returncode == 0:
            print("✅ 已自动同步到 MySQL（agent_time_tracking）。")
        else:
            tail = (r.stderr or r.stdout).strip().replace("\n", " ")[:400]
            print(f"⚠️ 自动同步 MySQL 失败（本地记录已保存，待计划任务重试）：{tail}", file=sys.stderr)
        return r.returncode
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ 自动同步异常（本地记录已保存）：{e}", file=sys.stderr)
        return 1


def check_prior_missing(
    skill_root: Path, biz_line: str, employee: str, user_story: str, step_code: str
) -> list[str]:
    """v6.3: 写盘前检查「编号更小」的追踪环节是否已记录，返回缺失的 step_code 列表。

    这是脚本级强制，不依赖提示词自觉——AI 无法静默跳过前序环节的补录。
    检测脚本缺失或调用失败时返回空列表（不因检测能力不可用而阻断业务落盘）。
    """
    script = skill_root / "scripts" / "check_missing_time_records.py"
    if not script.is_file():
        return []
    command = [
        sys.executable,
        str(script),
        "--biz-line",
        biz_line,
        "--employee",
        employee,
        "--user-story",
        user_story,
        "--current-step-code",
        step_code,
    ]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            check=False,
        )
        if result.returncode != 0:
            return []
        payload = json.loads(result.stdout)
        return list(payload.get("missing") or [])
    except (json.JSONDecodeError, TypeError, OSError, ValueError):
        return []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="通过 MySQL 花名册严格校验后记录节省工时（v1.0.1）"
    )
    parser.add_argument("--employee", required=True, help="员工姓名，精确匹配")
    parser.add_argument("--user-story", required=True, help="用户故事名称或编号")
    parser.add_argument("--step", required=True, help="步骤名称")
    parser.add_argument("--step-code", required=True, choices=SUPPORTED_STEP_CODES)
    parser.add_argument("--biz-line", required=True, choices=SUPPORTED_BUSINESS_LINES)
    value_group = parser.add_mutually_exclusive_group(required=True)
    value_group.add_argument("--hours", type=float, help="节省时间（小时）")
    value_group.add_argument("--person-days", type=float, help="节省时间（人天）")
    parser.add_argument("--remark", default="")
    parser.add_argument("--agent-start-time", default="")
    parser.add_argument("--agent-end-time", default="")
    parser.add_argument("--agent-duration-minutes", type=float, default=None)
    parser.add_argument("--ai-estimated-time-saved-hours", type=float, default=None)
    parser.add_argument(
        "--force-with-missing",
        action="store_true",
        help="v6.3: 前序环节缺失时仍强制写入。仅在已引导补录且人员明确回复「跳过」后使用",
    )
    parser.add_argument(
        "--missing-reason",
        default="",
        help="配合 --force-with-missing，说明前序环节未记录的原因（如「人员跳过环节01」）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        skill_root = time_tracking_skill_root()
        roster = query_roster(skill_root, args.biz_line)
    except (OSError, ValueError):
        print("身份验证失败，请联系管理员确认 MySQL 花名册服务可用。", file=sys.stderr)
        return 3
    if not authorize_employee(roster, args.employee, args.biz_line):
        print("身份验证失败，当前人员无权记录该业务线数据。", file=sys.stderr)
        return 3

    # v6.3: 脚本级强制 —— 写盘前检查前序追踪环节是否已记录，杜绝「跳步漏记」
    missing = check_prior_missing(
        skill_root, args.biz_line, args.employee, args.user_story, args.step_code
    )
    if missing and not args.force_with_missing:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "step_code": args.step_code,
                    "missing": missing,
                    "message": (
                        f"环节 {args.step_code} 的记录被拦截：检测到前序环节 "
                        f"{'、'.join(missing)} 尚未记录节省时间。"
                        "请先按编号升序逐个补录（人员可回复「跳过」），之后再对本环节重试；"
                        "若人员已明确跳过，请加 --force-with-missing 并用 --missing-reason 说明原因。"
                    ),
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2
    if missing and args.force_with_missing:
        print(
            f"⚠️ 前序环节 {'、'.join(missing)} 未记录，按 --force-with-missing 继续写入"
            f"（原因：{args.missing_reason or '未提供'}）",
            file=sys.stderr,
        )
        if args.missing_reason:
            args.remark = (
                f"{args.remark} [前序环节 {'、'.join(missing)} 未记录：{args.missing_reason}]"
            ).strip()

    result = subprocess.run(build_record_command(args, skill_root), check=False)
    if result.returncode != 0:
        return result.returncode
    # v6.1: 本地落盘成功后立即同步到 MySQL，不再依赖定时任务的时序
    sync_to_mysql_after_record(args.biz_line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
