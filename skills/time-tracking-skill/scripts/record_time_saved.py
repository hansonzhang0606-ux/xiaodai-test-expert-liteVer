#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
时间节省记录脚本 v6.2（通用多业务线版）
在工作流每个步骤完成后，记录该步骤为人类员工节省了多少时间。

v5.9 增量:
  - 新增 ai_estimated_time_saved_hours，可选且独立于人员反馈

v3 改进:
  - 二次确认：脚本仅负责记录，确认逻辑由 AI 在调用前完成
  - 统一存储单位：底层始终以小时存储，time_saved_pd 为换算值
  - Excel 同步：storage_mode=excel 时自动追加到 Excel 文件
  - 花名册校验 + 参考时间展示
  - biz_line 可配置：--biz-line 参数优先，未指定时读取
    config/time_tracking_config.yaml 的 default_biz_line

用法:
  python record_time_saved.py \
    --employee "张三" \
    --user-story "US-001-贷款审批流程优化" \
    --step "文档整理" \
    --step-code "01" \
    --hours 4.0 \
    --biz-line "智慧记+运营系统" \
    --agent-start-time "2026-08-27T09:05:00+08:00" \
    --agent-end-time "2026-08-27T09:17:30+08:00" \
    --agent-duration-minutes 12.5 \
    --remark "原本需要手动整理5个文档"

  # 也可以用人天为单位输入，脚本自动换算为小时存储
  python record_time_saved.py \
    --employee "李四" \
    --user-story "US-001" \
    --step "用例细化" \
    --step-code "06" \
    --person-days 1.5 \
    --biz-line "智慧记+运营系统"

数据存储位置:
  ~/.workbuddy/data/time-tracking/{biz_line}/records.jsonl
  （excel 模式下同时写入配置指定的 Excel 文件）
"""

import argparse
import json
import math
import os
import re
import sys
from datetime import datetime, timezone, timedelta


# 步骤代码映射
STEP_MAP = {
    "01": "文档整理",
    "02": "需求评审",
    "04": "生成测试点",
    "06": "用例细化",
    "07": "知识入库",
}

# 参考时间表
REFERENCE_TIMES = {
    "01": {"min": 2.0, "max": 4.0, "unit": "小时", "basis": "按文档数量浮动，5个以上取上限"},
    "02": {"min": 2.0, "max": 3.0, "unit": "小时", "basis": "6维度评审（完整性/一致性/边界/异常/优先级/可测性）"},
    "04": {"min": 3.0, "max": 5.0, "unit": "小时", "basis": "按需求复杂度浮动，多系统交互取上限"},
    "06": {"min": 4.0, "max": 8.0, "unit": "小时", "basis": "按用例数量浮动，100条以上取上限，可用人天"},
    "07": {"min": 1.0, "max": 2.0, "unit": "小时", "basis": "总结+差异对比+精华提炼+归档"},
}

# 人天换算（1人天 = 8小时）
HOURS_PER_PD = 8.0

# 故事编号提取正则：匹配 PRJ-00769736 / US-001 / P-12345 等「前缀-数字」格式
STORY_CODE_RE = re.compile(r"([A-Za-z]{1,8}-\d{3,})")


def extract_user_story_code(user_story: str) -> str:
    """从用户故事标题中提取编号（如 'PRJ-00769736-【效贷xxxx】OCR征信报告测额' → 'PRJ-00769736'）"""
    us = user_story or ""
    m = STORY_CODE_RE.search(us)
    if m:
        return m.group(1)
    m = re.search(r"\b\d{5,}\b", us)
    if m:
        return m.group(0)
    return ""


def normalize_ai_estimated_hours(value):
    """校验并规范化 AI 预估节省工时（小时）。"""
    if value is None:
        return None
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0:
        raise ValueError("ai_estimated_time_saved_hours 必须是大于等于 0 的有限小时数")
    return round(normalized, 2)

# 花名册缓存（实时从 MySQL agent_team_roster 查询）
_roster_cache = None


def get_skill_dir() -> str:
    """获取 skill 根目录"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_team_roster() -> dict:
    """加载花名册（实时从 MySQL agent_team_roster 查询，不再读 team_roster.yaml）

    返回兼容旧格式：{"members": [{"name", "role", "active", "biz_line_code", "biz_line"}, ...], "error": str|None}
    MySQL 配置缺失 / 连接失败时返回空花名册 + error 信息（上层可降级处理）。
    """
    global _roster_cache
    if _roster_cache is not None:
        return _roster_cache

    try:
        from load_roster import load_roster_from_mysql
        # 一次性查全部（含离职），便于区分"在职"/"已离职"/"不在花名册"
        roster, _cfg_path = load_roster_from_mysql(include_inactive=True)
    except Exception as e:
        _roster_cache = {"members": [], "error": str(e)}
        return _roster_cache

    members = []
    for name, info in roster.items():
        members.append({
            "name": name,
            "role": info.get("role") or "功能测试",
            "active": bool(info.get("active", True)),
            "biz_line_code": info.get("biz_line_code", []),
            "biz_line": info.get("biz_line", []),
        })
    _roster_cache = {"members": members, "error": None}
    return _roster_cache


def validate_employee(employee: str) -> tuple:
    """实时校验员工身份（MySQL agent_team_roster 表）

    返回 (is_valid, status, error_or_none)。status 取值：
      - "在职"：active=1，可正常服务
      - "已离职/停用"：active=0，已无权限
      - "不在花名册中"：从未入库
      - "花名册查询失败"：MySQL 配置缺失或连接失败
    """
    roster = load_team_roster()
    if roster.get("error"):
        return False, "花名册查询失败", roster["error"]
    members = roster.get("members", [])
    active_names = [m["name"] for m in members if m.get("active", True)]
    all_names = [m["name"] for m in members]

    if employee in active_names:
        return True, "在职", None
    elif employee in all_names:
        return False, "已离职/停用", None
    else:
        return False, "不在花名册中", None


def get_data_dir(biz_line: str) -> str:
    """获取数据存储目录，不存在则创建"""
    home = os.path.expanduser("~")
    data_dir = os.path.join(home, ".workbuddy", "data", "time-tracking", biz_line)
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def get_records_path(biz_line: str) -> str:
    """获取 records.jsonl 文件路径"""
    return os.path.join(get_data_dir(biz_line), "records.jsonl")


def record(
    employee: str,
    user_story: str,
    step: str,
    step_code: str,
    hours: float = None,
    person_days: float = None,
    biz_line: str = "",
    remark: str = "",
    agent_start_time: str = "",
    agent_end_time: str = "",
    agent_duration_minutes: float = None,
    skip_validation: bool = False,
    ai_estimated_time_saved_hours: float = None,
):
    """记录一条时间节省数据（biz_line 未指定时自动从配置解析）"""
    if not biz_line:
        from biz_line_helper import resolve_biz_line
        biz_line = resolve_biz_line("")
    # 花名册校验（实时查 MySQL agent_team_roster）
    if not skip_validation:
        valid, status, err = validate_employee(employee)
        if not valid and status == "花名册查询失败":
            print(f"⚠️  警告：花名册查询失败（{err}），无法校验员工身份。", file=sys.stderr)
            print(f"   本次记录仍会保存，但建议核实。", file=sys.stderr)
        elif not valid and status == "不在花名册中":
            print(f"⚠️  警告：员工 '{employee}' 不在花名册中。", file=sys.stderr)
            print(f"   花名册在职人员：{', '.join(m['name'] for m in load_team_roster().get('members', []) if m.get('active', True))}", file=sys.stderr)
            print(f"   如确为此员工，请联系管理员直接 INSERT/UPDATE `agent_team_roster` 表。", file=sys.stderr)
            print(f"   本次记录仍会保存，但建议核实。", file=sys.stderr)
        elif not valid and status == "已离职/停用":
            print(f"⚠️  警告：员工 '{employee}' 在花名册中标记为停用。", file=sys.stderr)

    # 统一换算为小时（v3：底层存储始终为小时）
    time_hours = 0.0
    time_pd = 0.0

    if hours is not None:
        time_hours += float(hours)
    if person_days is not None:
        time_pd += float(person_days)

    # 人天换算为小时，统一以小时为基准
    total_hours = round(time_hours + time_pd * HOURS_PER_PD, 2)
    # 人天 = 总小时 / 8
    time_pd = round(total_hours / HOURS_PER_PD, 2)
    time_hours = total_hours

    # 自动补全步骤名称
    if step_code and not step:
        step = STEP_MAP.get(step_code, step_code)
    if step and not step_code:
        for code, name in STEP_MAP.items():
            if name == step:
                step_code = code
                break

    now = datetime.now(timezone(timedelta(hours=8)))
    ai_estimated_hours = normalize_ai_estimated_hours(
        ai_estimated_time_saved_hours
    )

    record = {
        "timestamp": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "biz_line": biz_line,
        "employee": employee,
        "user_story": user_story,
        "user_story_code": extract_user_story_code(user_story),
        "step": step,
        "step_code": step_code,
        "time_saved_hours": time_hours,
        "time_saved_pd": time_pd,
        "total_hours": total_hours,
        "agent_start_time": agent_start_time or "",
        "agent_end_time": agent_end_time or "",
        "agent_duration_minutes": float(agent_duration_minutes) if agent_duration_minutes is not None else None,
        "ai_estimated_time_saved_hours": ai_estimated_hours,
        "remark": remark,
    }

    records_path = get_records_path(biz_line)

    with open(records_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # 输出参考时间
    ref = REFERENCE_TIMES.get(step_code, {})
    ref_str = ""
    if ref:
        ref_str = f"   参考时间: {ref['min']}~{ref['max']} {ref['unit']}（{ref['basis']}）\n"

    print(f"✅ 已记录时间节省数据")
    print(f"   员工: {employee}")
    print(f"   用户故事: {user_story}")
    code = record.get("user_story_code", "")
    if code:
        print(f"   故事编号: {code}")
    print(f"   步骤: {step} ({step_code})")
    print(f"   节省时间: {time_pd} 人天（{time_hours} 小时）")
    print(f"   存储单位: 小时（{total_hours}h）")
    if agent_start_time and agent_end_time:
        print(f"   智能体执行: {agent_start_time} → {agent_end_time}（{agent_duration_minutes} 分钟）")
    if ai_estimated_hours is not None:
        print(f"   AI 预估节省时间: {ai_estimated_hours} 小时（独立于人员反馈）")
    print(f"   业务线: {biz_line}")
    if ref_str:
        print(ref_str, end="")
    if remark:
        print(f"   备注: {remark}")
    print(f"   存储位置: {records_path}")

    # Excel 同步（storage_mode=excel 时，可选附加）
    try:
        sync_to_excel_if_configured(record, biz_line)
    except Exception as e:
        print(f"⚠️  Excel 同步失败（不影响本地记录）: {e}", file=sys.stderr)

    return record


def load_tracking_config() -> dict:
    """加载时间追踪配置"""
    config_path = os.path.join(get_skill_dir(), "config", "time_tracking_config.yaml")
    if not os.path.exists(config_path):
        return {}
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        # 简易解析
        config = {}
        with open(config_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("storage_mode:"):
                    config["storage_mode"] = line.split(":", 1)[1].strip().strip('"')
        return config


def sync_to_excel_if_configured(record: dict, biz_line: str):
    """如果配置了 excel 存储模式，将记录追加到 Excel"""
    config = load_tracking_config()
    storage_mode = config.get("storage_mode", "local")

    if storage_mode != "excel":
        return

    excel_config = config.get("excel", {})
    excel_path = excel_config.get("file_path", "")

    if not excel_path:
        print("⚠️  storage_mode=excel 但未配置 excel.file_path，跳过 Excel 同步", file=sys.stderr)
        return

    # 展开 ~ 为用户主目录
    excel_path = os.path.expanduser(excel_path)

    # 调用 sync_to_excel 的追加逻辑
    from sync_to_excel import append_record_to_excel
    append_record_to_excel(excel_path, record)
    print(f"📊 已同步到 Excel: {excel_path}")


def main():
    parser = argparse.ArgumentParser(description="记录时间节省数据 v6.2")
    parser.add_argument("--employee", required=True, help="员工姓名（需在花名册中）")
    parser.add_argument("--user-story", required=True, help="用户故事名称/编号")
    parser.add_argument("--step", default="", help="步骤名称（如：文档整理）")
    parser.add_argument("--step-code", default="", help="步骤代码（01/02/04/06/07）")
    parser.add_argument("--hours", type=float, default=None, help="节省时间（小时）")
    parser.add_argument("--person-days", type=float, default=None, help="节省时间（人天）")
    parser.add_argument("--biz-line", default="", help="业务线（未指定时读取 config 中 default_biz_line）")
    parser.add_argument("--remark", default="", help="备注")
    parser.add_argument("--agent-start-time", default="", help="智能体开始处理本步骤的 ISO 时间戳（如 2026-08-27T09:05:00+08:00）")
    parser.add_argument("--agent-end-time", default="", help="智能体完成本步骤的 ISO 时间戳（如 2026-08-27T09:17:30+08:00）")
    parser.add_argument("--agent-duration-minutes", type=float, default=None, help="智能体实际执行耗时（分钟）")
    parser.add_argument(
        "--ai-estimated-time-saved-hours",
        type=float,
        default=None,
        help="AI 预估本环节可节省时间（小时，独立于人员反馈）",
    )
    parser.add_argument("--skip-validation", action="store_true", help="跳过花名册校验")

    args = parser.parse_args()

    if args.hours is None and args.person_days is None:
        print("错误：必须指定 --hours 或 --person-days", file=sys.stderr)
        sys.exit(1)

    record(
        employee=args.employee,
        user_story=args.user_story,
        step=args.step,
        step_code=args.step_code,
        hours=args.hours,
        person_days=args.person_days,
        biz_line=args.biz_line,
        remark=args.remark,
        agent_start_time=args.agent_start_time,
        agent_end_time=args.agent_end_time,
        agent_duration_minutes=args.agent_duration_minutes,
        ai_estimated_time_saved_hours=args.ai_estimated_time_saved_hours,
        skip_validation=args.skip_validation,
    )


if __name__ == "__main__":
    main()
