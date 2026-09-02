#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
跨步骤时间节省记录缺失检查脚本 v6.0（通用多业务线版）

用途：
  测试人员可能在某环节尚未进入「完成」态时就跳到下一环节（例如环节 ① 还在迭代
  就跳到 ②），导致该环节的节省时间从未被询问与记录。本脚本在进入新的追踪环节前，
  扫描本地 records.jsonl，找出同一 (员工, 用户故事) 下、编号更小但尚未记录的
  追踪环节，供 AI 在触发本步骤时间钩子前先行补录。

追踪环节：01 / 02 / 04 / 06 / 07（环节 3 确认评审、5 评审 XMind 不追踪）

用法:
  python check_missing_time_records.py \
    --biz-line "小贷" \
    --employee "何甜" \
    --user-story "PRJ-00768348-【小贷】OCR征信报告测额" \
    --current-step-code "02"

输出 JSON:
  {
    "status": "ok",
    "biz_line": "小贷",
    "employee": "何甜",
    "user_story": "PRJ-00768348-【小贷】OCR征信报告测额",
    "user_story_code": "PRJ-00768348",
    "current_step_code": "02",
    "candidates": ["01"],
    "recorded": [],
    "missing": ["01"],
    "missing_detail": [{"step_code": "01", "step_name": "需求文档整理"}],
    "records_path": "C:\\Users\\...\\time-tracking\\小贷\\records.jsonl"
  }

退出码:
  0  正常（无论是否有缺失）
  1  参数错误
"""

import argparse
import json
import os
import re
import sys


# Windows 控制台可能是 GBK，强制以 UTF-8 输出中文 JSON
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


# 追踪步骤代码（环节 3/5 不追踪）
TRACKED_STEP_CODES = ["01", "02", "04", "06", "07"]

# 步骤代码 → 环节名称（与编排器 step_mapping.yaml 对齐）
STEP_NAMES = {
    "01": "需求文档整理",
    "02": "需求评审",
    "04": "生成测试点",
    "06": "生成用例",
    "07": "知识库入库",
}

# 故事编号提取正则：匹配 PRJ-00769736 / US-001 / P-12345 等「前缀-数字」格式
STORY_CODE_RE = re.compile(r"([A-Za-z]{1,8}-\d{3,})")


def extract_user_story_code(user_story: str) -> str:
    """从用户故事标题中提取编号（如 'PRJ-00768348-【小贷】xxx' → 'PRJ-00768348'）"""
    us = user_story or ""
    m = STORY_CODE_RE.search(us)
    if m:
        return m.group(1)
    m = re.search(r"\b\d{5,}\b", us)
    if m:
        return m.group(0)
    return ""


def get_records_path(biz_line: str) -> str:
    """获取 records.jsonl 文件路径（与 record_time_saved.py 保持一致）"""
    home = os.path.expanduser("~")
    return os.path.join(home, ".workbuddy", "data", "time-tracking", str(biz_line), "records.jsonl")


def match_user_story(record: dict, user_story: str, story_code: str) -> bool:
    """匹配用户故事：优先按 user_story_code，无编号时退化为 user_story 精确匹配"""
    if story_code:
        return (record.get("user_story_code") or "").strip() == story_code
    return (record.get("user_story") or "").strip() == (user_story or "").strip()


def collect_recorded_codes(records_path: str, employee: str, user_story: str, story_code: str) -> set:
    """扫描 records.jsonl，收集该 (员工, 用户故事) 已记录的追踪步骤代码"""
    recorded = set()
    if not os.path.exists(records_path):
        return recorded
    with open(records_path, "r", encoding="utf-8") as f:
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
            if not match_user_story(rec, user_story, story_code):
                continue
            code = (rec.get("step_code") or "").strip()
            if code:
                recorded.add(code)
    return recorded


def check_missing(biz_line: str, employee: str, user_story: str, current_step_code: str = "", steps: str = "") -> dict:
    """检查缺失的追踪环节记录。

    steps: 逗号分隔的自定义检查集合（如 "01,04,06"），用于主链路核验；
           留空时回退到 TRACKED_STEP_CODES 全部追踪环节。
    current_step_code: 指定时只检查编号严格小于它的环节（进入下一环节前补录）。
    """
    records_path = get_records_path(biz_line)
    story_code = extract_user_story_code(user_story)
    recorded = collect_recorded_codes(records_path, employee, user_story, story_code)

    if steps:
        candidate_set = [s.strip() for s in steps.split(",") if s.strip()]
    else:
        candidate_set = list(TRACKED_STEP_CODES)

    # 只检查编号严格小于当前步骤的追踪环节（当前步骤的时间会在正常流程中询问）
    # 步骤代码为定长两位字符串，字典序与数值序一致
    if current_step_code and current_step_code in candidate_set:
        candidates = [c for c in candidate_set if c < current_step_code]
    else:
        candidates = list(candidate_set)

    missing = [c for c in candidates if c not in recorded]
    recorded_sorted = sorted(c for c in TRACKED_STEP_CODES if c in recorded)

    return {
        "status": "ok",
        "biz_line": biz_line,
        "employee": employee,
        "user_story": user_story,
        "user_story_code": story_code,
        "current_step_code": current_step_code or "",
        "candidates": candidates,
        "recorded": recorded_sorted,
        "missing": missing,
        "missing_detail": [
            {"step_code": c, "step_name": STEP_NAMES.get(c, c)} for c in missing
        ],
        "records_path": records_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="检查跨步骤缺失的时间节省记录 v6.0")
    parser.add_argument("--biz-line", required=True, help="业务线名称（如 效贷/效融/小贷）")
    parser.add_argument("--employee", required=True, help="员工姓名")
    parser.add_argument("--user-story", required=True, help="用户故事名称或编号")
    parser.add_argument(
        "--current-step-code",
        default="",
        help="当前步骤代码（01/02/04/06/07）；指定时只检查编号更小的环节，留空则检查全部追踪环节",
    )
    parser.add_argument(
        "--steps",
        default="",
        help="逗号分隔的自定义检查环节集合，如 01,04,06（主链路核验）；留空则检查全部追踪环节",
    )
    args = parser.parse_args()

    current = (args.current_step_code or "").strip()
    if current and current not in TRACKED_STEP_CODES:
        print(
            f"错误：--current-step-code 必须是 {TRACKED_STEP_CODES} 之一，收到 '{current}'",
            file=sys.stderr,
        )
        return 1

    result = check_missing(
        biz_line=args.biz_line,
        employee=args.employee,
        user_story=args.user_story,
        current_step_code=current,
        steps=args.steps,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
