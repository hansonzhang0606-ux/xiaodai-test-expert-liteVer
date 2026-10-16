#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_state.py - xmind 用例 -> weknora 上传状态跟踪，供专家每个步骤收尾时检查与提醒。

状态文件默认：<当前工作区>/.workbuddy/weknora_sync_state.json
可用 --state 指定其它路径（例如把状态随专家项目走）。

标签追踪（方案 C）：weknora MCP 无法写入/读回标签，标签需人工在网页端勾选。
本脚本用 tag_status 记录打标进度，供步骤收尾时提醒「还有 N 份已上传但未打标」：
  pending = 待人工打标（status 变为 uploaded 时自动置此值）
  done    = 已在网页端打标确认
  na      = 无需打标（如已跳过上传）

用法:
  python sync_state.py check --key "PRJ-00770309|测试用例"
  python sync_state.py mark  --key "PRJ-00770309|测试用例" --status uploaded \
         --kb "效贷_测试_测试用例" --title "..." --doc-id "..." --md-path "..." --xmind-path "..." \
         --tag "测试用例"
  python sync_state.py mark  --key "PRJ-00770309|测试用例" --tag-status done   # 打标完成后
  python sync_state.py list [--pending] [--untagged]
  python sync_state.py clear --key "..."        # 删除一条记录

退出码（check）: 0=已上传；10=待上传(pending)；11=明确跳过(skipped)；12=无记录
  （标签不影响退出码；JSON 中 tag_status / tag_reminder 字段供智能体提醒用）
"""

import argparse
import json
import os
import sys
from datetime import datetime

DEFAULT_NAME = "weknora_sync_state.json"

TAG_STATUSES = ("pending", "done", "na")
MANUAL_STEPS_SHORT = "知识库页 → 勾选文档 → 标签 → 添加标签 → 选择「{tag}」→ 确定"


def default_state_path():
    return os.path.join(os.getcwd(), ".workbuddy", DEFAULT_NAME)


def tag_reminder(rec):
    """对已上传但未打标的记录生成提醒文案；无需提醒时返回空串。"""
    if rec.get("status") != "uploaded":
        return ""
    if rec.get("tag_status") in ("done", "na"):
        return ""
    tag = rec.get("tag") or ""
    kb = rec.get("kb") or ""
    if not tag:
        return "已上传但缺标签信息，请与测试人员确认文档类型对应的标签"
    return (f"已上传但尚未在 weknora 打标签「{tag}」：{kb} → {MANUAL_STEPS_SHORT.format(tag=tag)}；"
            f"打完请执行 sync_state.py mark --key \"{rec.get('key','')}\" --tag-status done")


def load(path):
    if not os.path.isfile(path):
        return {"records": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {"records": []}


def save(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def find(records, key):
    for r in records:
        if r.get("key") == key:
            return r
    return None


def main():
    ap = argparse.ArgumentParser(description="xmind 用例上传状态跟踪")
    ap.add_argument("command", choices=["check", "mark", "list", "clear"])
    ap.add_argument("--key", help="记录键，建议 用户故事|文档类型，如 PRJ-00770309|测试用例")
    ap.add_argument("--status", choices=["pending", "uploaded", "skipped"], help="mark 时的状态")
    ap.add_argument("--kb", help="目标知识库名称")
    ap.add_argument("--title", help="weknora 文档标题")
    ap.add_argument("--doc-id", help="weknora 文档 ID")
    ap.add_argument("--md-path", help="本地 Markdown 路径")
    ap.add_argument("--xmind-path", help="本地 xmind 源路径")
    ap.add_argument("--biz-line", help="业务线")
    ap.add_argument("--tag", help="weknora 标签名（= 文档类型，如 测试用例 / 测试总结 / 测试需求分析 / 测试缺陷）")
    ap.add_argument("--tag-status", choices=TAG_STATUSES, help="打标进度：pending 待打标 / done 已打标 / na 无需打标")
    ap.add_argument("--note", help="备注")
    ap.add_argument("--state", help="状态文件路径")
    ap.add_argument("--pending", action="store_true", help="list 时仅显示未上传")
    ap.add_argument("--untagged", action="store_true", help="list 时仅显示已上传但未打标签的")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    path = args.state or default_state_path()
    data = load(path)
    all_records = data.get("records", [])

    if args.command == "list":
        records = all_records
        if args.pending:
            records = [r for r in records if r.get("status") != "uploaded"]
        if args.untagged:
            records = [r for r in records if r.get("status") == "uploaded"
                       and r.get("tag_status") not in ("done", "na")]
        untagged_total = sum(1 for r in all_records if r.get("status") == "uploaded"
                             and r.get("tag_status") not in ("done", "na"))
        if args.json:
            print(json.dumps({"records": records, "untagged_total": untagged_total},
                             ensure_ascii=False, indent=2))
        else:
            if not records:
                print("（无记录）")
            for r in records:
                tag = r.get("tag") or "-"
                ts = r.get("tag_status") or "pending"
                mark = {"done": "已打标", "na": "无需打标"}.get(ts, "待打标")
                print(f"[{r.get('status')}|标签:{tag}|{mark}] {r.get('key')} -> {r.get('kb','')} "
                      f"| {r.get('title','')} | {r.get('updated_at','')}")
            if untagged_total:
                print(f"\n⚠️  共 {untagged_total} 份已上传但尚未打标签（MCP 无法自动写入，需人工在网页端勾选）。")
                print("   打完标后：sync_state.py mark --key \"<键>\" --tag-status done")
        return

    if not args.key:
        print("[错误] check/mark/clear 必须提供 --key", file=sys.stderr)
        raise SystemExit(1)

    if args.command == "check":
        rec = find(data.get("records", []), args.key)
        if rec is None:
            print(json.dumps({"key": args.key, "status": "none", "state_path": path}, ensure_ascii=False))
            raise SystemExit(12)
        status = rec.get("status")
        untagged_total = sum(1 for r in all_records if r.get("status") == "uploaded"
                             and r.get("tag_status") not in ("done", "na"))
        out = {**rec, "state_path": path,
               "tag_reminder": tag_reminder(rec),
               "untagged_total": untagged_total}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        raise SystemExit({"uploaded": 0, "pending": 10, "skipped": 11}.get(status, 12))

    if args.command == "clear":
        before = len(data.get("records", []))
        data["records"] = [r for r in data.get("records", []) if r.get("key") != args.key]
        save(path, data)
        print(f"[已删除] {args.key}（{before} -> {len(data['records'])}）")
        return

    # mark
    if not args.status and not args.tag_status and not args.tag:
        print("[错误] mark 需提供 --status 或 --tag-status 或 --tag", file=sys.stderr)
        raise SystemExit(1)
    rec = find(data["records"], args.key)
    if rec is None:
        rec = {"key": args.key}
        data["records"].append(rec)
    if args.status:
        rec["status"] = args.status
        # 上传成功即进入「待人工打标」；其它状态无需打标
        if args.status == "uploaded":
            rec.setdefault("tag_status", "pending")
            if rec.get("tag_status") == "na":
                rec["tag_status"] = "pending"
        elif args.status in ("pending", "skipped"):
            rec["tag_status"] = "na"
    if args.tag:
        rec["tag"] = args.tag
    if args.tag_status:
        rec["tag_status"] = args.tag_status
    rec.update({
        "biz_line": args.biz_line or rec.get("biz_line", ""),
        "kb": args.kb or rec.get("kb", ""),
        "title": args.title or rec.get("title", ""),
        "doc_id": args.doc_id or rec.get("doc_id", ""),
        "md_path": args.md_path or rec.get("md_path", ""),
        "xmind_path": args.xmind_path or rec.get("xmind_path", ""),
        "note": args.note or rec.get("note", ""),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    if rec.get("status") == "uploaded" and "tag_status" not in rec:
        rec["tag_status"] = "pending"
    save(path, data)
    desc = args.status or f"标签={rec.get('tag_status','')}"
    print(f"[已记录] {args.key} -> {desc}（{path}）")
    tip = tag_reminder(rec)
    if tip:
        print(f"  ⚠️  {tip}")


if __name__ == "__main__":
    main()
