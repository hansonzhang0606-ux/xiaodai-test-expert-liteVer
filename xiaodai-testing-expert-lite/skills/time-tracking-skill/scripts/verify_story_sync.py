#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
核查某用户故事的时间节省记录是否已同步到 MySQL v6.1（通用多业务线版）

用途：
    主链路（01/04/06）全部完成后，或会话收尾时，作为双保险核查：
    读本地 records.jsonl 确定已记录环节，再查 MySQL agent_time_tracking
    确认是否入库；输出未同步环节，便于立即触发同步。

用法:
  python verify_story_sync.py \
    --biz-line "小贷" \
    --employee "张云星" \
    --user-story "PRJ-00768348【小贷260827】结清证明申请加盖签章" \
    --steps "01,04,06"

输出 JSON:
  {
    "status": "ok" | "db_error",
    "local_recorded": ["01","04","06"],
    "synced_in_db": ["01","04"],
    "unsynced": ["06"],
    "db_error": null | "连接异常信息"
  }

退出码:
  0  全部已同步（或无本地记录）
  2  存在未同步环节
  1  参数/运行错误
"""

import argparse
import json
import os
import re
import sys

# 让脚本可独立运行：优先加载同目录打包的 pymysql（离线可用）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.isdir(os.path.join(SCRIPT_DIR, "pymysql")):
    sys.path.insert(0, SCRIPT_DIR)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    import pymysql
    import pymysql.cursors
except ImportError:
    print("ERROR: pymysql 未打包进脚本目录。请确认 scripts/pymysql/ 存在。", file=sys.stderr)
    sys.exit(1)

from biz_line_helper import resolve_biz_line, BIZ_LINE_CODE_MAP


STORY_CODE_RE = re.compile(r"([A-Za-z]{1,8}-\d{3,})")


def extract_user_story_code(user_story: str) -> str:
    us = user_story or ""
    m = STORY_CODE_RE.search(us)
    if m:
        return m.group(1)
    m = re.search(r"\b\d{5,}\b", us)
    return m.group(0) if m else ""


def get_records_path(biz_line: str) -> str:
    return os.path.join(
        os.path.expanduser("~"), ".workbuddy", "data", "time-tracking", str(biz_line), "records.jsonl"
    )


def local_recorded_codes(path: str, employee: str, story_code: str) -> set:
    codes = set()
    if not os.path.exists(path):
        return codes
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            if (rec.get("employee") or "").strip() != (employee or "").strip():
                continue
            if (rec.get("user_story_code") or "").strip() != (story_code or "").strip():
                continue
            c = (rec.get("step_code") or "").strip()
            if c:
                codes.add(c)
    return codes


def main() -> int:
    parser = argparse.ArgumentParser(description="核查时间记录是否已同步到 MySQL v6.1")
    parser.add_argument("--biz-line", required=True, help="业务线名称")
    parser.add_argument("--employee", required=True, help="员工姓名")
    parser.add_argument("--user-story", required=True, help="用户故事名称或编号")
    parser.add_argument(
        "--steps",
        default="",
        help="逗号分隔的检查环节，如 01,04,06；留空则检查本地已记录的全部环节",
    )
    args = parser.parse_args()

    biz_line = args.biz_line
    story_code = extract_user_story_code(args.user_story)
    biz_line_code = BIZ_LINE_CODE_MAP.get(resolve_biz_line(biz_line), "")
    path = get_records_path(biz_line)
    local = local_recorded_codes(path, args.employee, story_code)

    steps = [s.strip() for s in args.steps.split(",") if s.strip()] if args.steps else []
    local_relevant = sorted(c for c in local if (not steps or c in steps))

    cfg_path = os.path.join(
        os.path.expanduser("~"), ".workbuddy", "data", "time-tracking", biz_line, "mysql_config.json"
    )
    synced: set = set()
    db_error = None
    if os.path.exists(cfg_path):
        cfg = json.load(open(cfg_path, "r", encoding="utf-8"))
        try:
            conn = pymysql.connect(
                host=cfg.get("host", "127.0.0.1"),
                port=int(cfg.get("port", 3306)),
                user=cfg.get("user", "root"),
                password=cfg.get("password", ""),
                database=cfg.get("database", ""),
                charset=cfg.get("charset", "utf8mb4"),
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=10,
            )
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT step_code FROM agent_time_tracking "
                        "WHERE biz_line_code=%s AND employee=%s AND user_story_code=%s",
                        (biz_line_code, args.employee, story_code),
                    )
                    synced = {r["step_code"] for r in cur.fetchall()}
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001
            db_error = str(e)
    else:
        db_error = f"配置文件不存在: {cfg_path}"

    unsynced = sorted(c for c in local_relevant if c not in synced)
    out = {
        "status": "ok" if db_error is None else "db_error",
        "biz_line": biz_line,
        "employee": args.employee,
        "user_story": args.user_story,
        "user_story_code": story_code,
        "biz_line_code": biz_line_code,
        "local_recorded": local_relevant,
        "synced_in_db": sorted(c for c in local_relevant if c in synced),
        "unsynced": unsynced,
        "db_error": db_error,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if db_error is not None:
        return 1
    return 0 if not unsynced else 2


if __name__ == "__main__":
    raise SystemExit(main())
