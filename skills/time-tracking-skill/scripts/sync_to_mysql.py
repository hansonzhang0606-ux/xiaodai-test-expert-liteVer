#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
时间节省数据同步到 MySQL v6.3（通用多业务线版）

读取本地 JSONL 记录，幂等 upsert 到 MySQL 的 agent_time_tracking 表。
pymysql 已打包进本脚本同目录（scripts/pymysql/），无需 pip install，离线可用。

用法:
  python sync_to_mysql.py                 # 同步 config 中 default_biz_line 指定的业务线
  python sync_to_mysql.py --biz-line 智慧记+运营系统  # 指定业务线
  python sync_to_mysql.py --since 2026-08-17  # 只同步该日期及之后的记录
  python sync_to_mysql.py --dry-run       # 试运行，只看不写

数据源: ~/.workbuddy/data/time-tracking/{biz_line}/records.jsonl
配置:   ~/.workbuddy/data/time-tracking/{biz_line}/mysql_config.json
幂等:   唯一键 record_key = MD5(biz_line_code|employee|user_story|step_code|timestamp秒)
        INSERT ... ON DUPLICATE KEY UPDATE 处理同一条本地记录重同步（按 record_key 更新其余字段）；
        另按业务字段组合 (biz_line_code, employee, user_story_code, step_code, time_saved_hours)
        做去重预检，相同组合视为同一业务动作，避免不同 timestamp 但业务相同的记录重复入库。
v5.9:   目标表存在 ai_estimated_time_saved_hours 时同步该字段；不存在时保留 v5.8 同步路径。
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime

# 让脚本可独立运行：优先加载同目录打包的 pymysql（离线可用）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.isdir(os.path.join(SCRIPT_DIR, "pymysql")):
    sys.path.insert(0, SCRIPT_DIR)

from biz_line_helper import resolve_biz_line

try:
    import pymysql
    import pymysql.cursors
except ImportError:
    print("ERROR: pymysql 未打包进脚本目录。请确认 scripts/pymysql/ 存在。", file=sys.stderr)
    sys.exit(1)

# 业务线中文名 -> 编码（与 init_mysql.sql 注释一致，统一维护在 biz_line_helper.py）
from biz_line_helper import BIZ_LINE_CODE_MAP as BIZ_LINE_CODE_MAP

HOME = os.path.expanduser("~")
AI_ESTIMATE_COLUMN = "ai_estimated_time_saved_hours"


def get_data_dir(biz_line):
    return os.path.join(HOME, ".workbuddy", "data", "time-tracking", biz_line)


def load_mysql_config(biz_line):
    """读取本地 MySQL 配置（机器本地，不进 Git）"""
    cfg_path = os.path.join(get_data_dir(biz_line), "mysql_config.json")
    if not os.path.exists(cfg_path):
        print(f"ERROR: 配置文件不存在: {cfg_path}", file=sys.stderr)
        print("请运行以下命令初始化（会提示输入密码）：", file=sys.stderr)
        print(f"   python init_mysql_config.py --biz-line {biz_line}", file=sys.stderr)
        print("字段模板见 scripts/mysql_config.json.template", file=sys.stderr)
        sys.exit(1)
    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_connection(cfg):
    return pymysql.connect(
        host=cfg.get("host", "127.0.0.1"),
        port=int(cfg.get("port", 3306)),
        user=cfg.get("user", "root"),
        password=cfg.get("password", ""),
        database=cfg.get("database", ""),
        charset=cfg.get("charset", "utf8mb4"),
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
    )


def table_has_column(conn, table, column):
    """检查当前数据库目标表是否包含指定列。"""
    sql = """
        SELECT COUNT(*) AS column_count
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (table, column))
        row = cur.fetchone() or {}
    return int(row.get("column_count", 0)) > 0


def normalize_timestamp(ts):
    """把 ISO 时间戳归一化为 '%Y-%m-%d %H:%M:%S'（秒级，MySQL DATETIME）"""
    ts = ts or ""
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ts[:19].replace("T", " ") if ts else None


def compute_record_key(record, biz_line_code):
    """幂等唯一键 MD5(biz_line_code|employee|user_story|step_code|timestamp秒)"""
    ts_sec = normalize_timestamp(record.get("timestamp")) or ""
    key_str = "|".join([
        biz_line_code,
        record.get("employee", "") or "",
        record.get("user_story", "") or "",
        record.get("step_code", "") or "",
        ts_sec,
    ])
    return hashlib.md5(key_str.encode("utf-8")).hexdigest()


# 故事编号提取正则：匹配 PRJ-00769736 / US-001 / P-12345 等「前缀-数字」格式
STORY_CODE_RE = re.compile(r"([A-Za-z]{1,8}-\d{3,})")


def extract_user_story_code(record):
    """提取故事编号：优先取记录自带 user_story_code 字段；
    否则从 user_story 标题中正则提取（如 'PRJ-00769736-【效贷xxxx】OCR征信报告测额' → 'PRJ-00769736'）。"""
    code = (record.get("user_story_code") or "").strip()
    if code:
        return code
    us = record.get("user_story", "") or ""
    m = STORY_CODE_RE.search(us)
    if m:
        return m.group(1)
    # 兜底：纯数字编号（如 "00769736"）
    m = re.search(r"\b\d{5,}\b", us)
    if m:
        return m.group(0)
    return ""


def read_jsonl_records(biz_line):
    """读取本地 JSONL 记录"""
    jsonl = os.path.join(get_data_dir(biz_line), "records.jsonl")
    if not os.path.exists(jsonl):
        return []
    records = []
    with open(jsonl, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def record_key_exists(conn, table, record_key):
    """判断 record_key 是否已存在于目标表（区分'同一条记录重同步'与'新记录'）"""
    sql = f"SELECT COUNT(*) AS cnt FROM {table} WHERE record_key=%s"
    with conn.cursor() as cur:
        cur.execute(sql, (record_key,))
        row = cur.fetchone() or {}
    return int(row.get("cnt", 0)) > 0


def business_dup_exists(conn, table, biz_line_code, employee, user_story_code, step_code, time_saved_hours):
    """业务字段去重：5 字段组合已存在则视为重复业务动作，避免不同 timestamp 的记录重复入库"""
    sql = f"""
        SELECT COUNT(*) AS cnt FROM {table}
        WHERE biz_line_code=%s AND employee=%s AND user_story_code=%s
          AND step_code=%s AND time_saved_hours=%s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (biz_line_code, employee, user_story_code, step_code,
                          float(time_saved_hours)))
        row = cur.fetchone() or {}
    return int(row.get("cnt", 0)) > 0


def upsert_record(
    conn,
    table,
    record,
    biz_line,
    biz_line_code,
    include_ai_estimate=False,
):
    """幂等 upsert 一条记录（record_key 唯一键兜底；额外按业务字段组合去重）"""
    record_key = compute_record_key(record, biz_line_code)
    user_story_code = extract_user_story_code(record)
    ts = normalize_timestamp(record.get("timestamp"))
    date_val = record.get("date", "") or (ts[:10] if ts else "")

    # —— 业务字段去重：相同 (biz_line_code, employee, user_story_code, step_code, time_saved_hours)
    #     视为同一业务动作。不同 timestamp 但业务字段相同 → 跳过，不重复入库。
    #     若 record_key 已存在，说明是同一条本地记录重同步，仍走 upsert 更新其余字段。 ——
    _employee = record.get("employee", "") or ""
    _step_code = record.get("step_code", "") or ""
    _hours = float(record.get("time_saved_hours", 0) or 0)
    if not record_key_exists(conn, table, record_key) and \
       business_dup_exists(conn, table, biz_line_code, _employee, user_story_code, _step_code, _hours):
        return "skipped_dup"

    sql = f"""
        INSERT INTO {table}
            (record_key, timestamp, date, biz_line, biz_line_code, employee, user_story,
             user_story_code, step, step_code, time_saved_hours, time_saved_pd, total_hours,
             agent_start_time, agent_end_time, agent_duration_minutes, remark)
        VALUES (%(record_key)s, %(timestamp)s, %(date)s, %(biz_line)s, %(biz_line_code)s,
                %(employee)s, %(user_story)s, %(user_story_code)s, %(step)s, %(step_code)s,
                %(time_saved_hours)s, %(time_saved_pd)s, %(total_hours)s,
                %(agent_start_time)s, %(agent_end_time)s, %(agent_duration_minutes)s, %(remark)s)
        ON DUPLICATE KEY UPDATE
            timestamp=VALUES(timestamp), date=VALUES(date),
            user_story=VALUES(user_story), user_story_code=VALUES(user_story_code),
            step=VALUES(step), step_code=VALUES(step_code),
            time_saved_hours=VALUES(time_saved_hours),
            time_saved_pd=VALUES(time_saved_pd),
            total_hours=VALUES(total_hours),
            agent_start_time=VALUES(agent_start_time),
            agent_end_time=VALUES(agent_end_time),
            agent_duration_minutes=VALUES(agent_duration_minutes),
            remark=VALUES(remark)
    """
    params = {
        "record_key": record_key,
        "timestamp": ts,
        "date": date_val,
        "biz_line": record.get("biz_line", "") or biz_line,
        "biz_line_code": biz_line_code,
        "employee": record.get("employee", ""),
        "user_story": record.get("user_story", ""),
        "user_story_code": user_story_code,
        "step": record.get("step", ""),
        "step_code": record.get("step_code", ""),
        "time_saved_hours": float(record.get("time_saved_hours", 0)),
        "time_saved_pd": float(record.get("time_saved_pd", 0)),
        "total_hours": float(record.get("total_hours", 0)),
        "agent_start_time": normalize_timestamp(record.get("agent_start_time")),
        "agent_end_time": normalize_timestamp(record.get("agent_end_time")),
        "agent_duration_minutes": float(record.get("agent_duration_minutes")) if record.get("agent_duration_minutes") not in (None, "") else None,
        "remark": record.get("remark", ""),
    }
    if include_ai_estimate:
        raw_ai_estimate = record.get(AI_ESTIMATE_COLUMN)
        params[AI_ESTIMATE_COLUMN] = (
            float(raw_ai_estimate)
            if raw_ai_estimate not in (None, "")
            else None
        )
        sql = f"""
            INSERT INTO {table}
                (record_key, timestamp, date, biz_line, biz_line_code, employee, user_story,
                 user_story_code, step, step_code, time_saved_hours, time_saved_pd, total_hours,
                 agent_start_time, agent_end_time, agent_duration_minutes,
                 ai_estimated_time_saved_hours, remark)
            VALUES (%(record_key)s, %(timestamp)s, %(date)s, %(biz_line)s, %(biz_line_code)s,
                    %(employee)s, %(user_story)s, %(user_story_code)s, %(step)s, %(step_code)s,
                    %(time_saved_hours)s, %(time_saved_pd)s, %(total_hours)s,
                    %(agent_start_time)s, %(agent_end_time)s, %(agent_duration_minutes)s,
                    %(ai_estimated_time_saved_hours)s, %(remark)s)
            ON DUPLICATE KEY UPDATE
                timestamp=VALUES(timestamp), date=VALUES(date),
                user_story=VALUES(user_story), user_story_code=VALUES(user_story_code),
                step=VALUES(step), step_code=VALUES(step_code),
                time_saved_hours=VALUES(time_saved_hours),
                time_saved_pd=VALUES(time_saved_pd),
                total_hours=VALUES(total_hours),
                agent_start_time=VALUES(agent_start_time),
                agent_end_time=VALUES(agent_end_time),
                agent_duration_minutes=VALUES(agent_duration_minutes),
                ai_estimated_time_saved_hours=VALUES(ai_estimated_time_saved_hours),
                remark=VALUES(remark)
        """
    with conn.cursor() as cur:
        cur.execute(sql, params)
    return "upserted"


def main():
    parser = argparse.ArgumentParser(description="时间节省数据同步到 MySQL（通用多业务线版）")
    parser.add_argument("--biz-line", default="", help="业务线（未指定时读取 config 中 default_biz_line）")
    parser.add_argument("--since", default="", help="只同步该日期及之后的记录（YYYY-MM-DD）")
    parser.add_argument("--dry-run", action="store_true", help="试运行，只看不写")
    args = parser.parse_args()

    biz_line = resolve_biz_line(args.biz_line)
    biz_line_code = BIZ_LINE_CODE_MAP.get(biz_line, "")
    if not biz_line_code:
        print(f"⚠️  业务线 '{biz_line}' 无预置编码（将写入空编码）。", file=sys.stderr)
        print(f"   已知编码映射: {BIZ_LINE_CODE_MAP}", file=sys.stderr)

    records = read_jsonl_records(biz_line)
    if args.since:
        records = [r for r in records if (r.get("date") or "") >= args.since]
    print("=" * 62)
    print(f"时间记录同步到 MySQL — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 62)
    print(f"业务线: {biz_line} ({biz_line_code})")
    print(f"本地记录: {len(records)} 条")

    if not records:
        print("✅ 没有待同步的记录。")
        return

    cfg = load_mysql_config(biz_line)
    table = cfg.get("table", "agent_time_tracking")

    if args.dry_run:
        print(f"\n🔍 试运行 — 将同步到 {cfg.get('host')}:{cfg.get('port')}/"
              f"{cfg.get('database')}.{table}:")
        for r in records:
            print(f"  {r.get('date')} | {r.get('employee')} | {r.get('step_code')} "
                  f"{r.get('step')} | {r.get('total_hours')}h")
        print(f"\n共 {len(records)} 条（未实际写入）")
        return

    conn = get_connection(cfg)
    print(f"✅ 已连接 MySQL: {cfg.get('host')}:{cfg.get('port')}/"
          f"{cfg.get('database')}.{table}")
    include_ai_estimate = table_has_column(conn, table, AI_ESTIMATE_COLUMN)
    if not include_ai_estimate:
        print(
            "⚠️  目标表尚无 ai_estimated_time_saved_hours 列；"
            "本次按 v5.8 字段同步，AI 预估仍保留在本地 JSONL。",
            file=sys.stderr,
        )

    ok = 0
    fail = 0
    skipped = 0
    for r in records:
        try:
            status = upsert_record(
                conn,
                table,
                r,
                biz_line,
                biz_line_code,
                include_ai_estimate=include_ai_estimate,
            )
            if status == "skipped_dup":
                skipped += 1
                print(f"  ⏭️  跳过(业务重复): {r.get('date')} | {r.get('employee')} | "
                      f"{r.get('step_code')} {r.get('step')} | {r.get('total_hours')}h")
            else:
                ok += 1
                print(f"  ✅ {r.get('date')} | {r.get('employee')} | {r.get('step_code')} "
                      f"{r.get('step')} | {r.get('total_hours')}h")
        except Exception as e:
            fail += 1
            print(f"  ❌ {r.get('date')} | {r.get('employee')} | {r.get('step')} → {e}")

    conn.commit()
    conn.close()

    print("\n" + "=" * 62)
    print(f"同步完成: 成功 {ok} 条 / 跳过(重复) {skipped} 条 / 失败 {fail} 条 / 合计 {len(records)} 条")
    print("=" * 62)

    if fail > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
