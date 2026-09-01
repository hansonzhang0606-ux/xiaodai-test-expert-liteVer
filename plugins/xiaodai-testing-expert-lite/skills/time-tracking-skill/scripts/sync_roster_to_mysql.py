#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【DEPRECATED 已弃用】花名册同步脚本（原：读 team_roster.yaml → upsert 到 MySQL agent_team_roster）

⚠️ 本脚本已弃用：自 v1.5.2 起 team_roster.yaml 不再作为数据源，花名册人员由管理员**直接维护在 MySQL agent_team_roster 表**（INSERT/UPDATE）。误运行本脚本不会改动 MySQL 数据（空 members 时仅打印「没有需要同步的成员」）。

（旧逻辑，仅供回顾）读取 config/team_roster.yaml（原唯一数据源），把成员按业务线展开后幂等 upsert 到
MySQL 的 agent_team_roster 表（跨业务线共享，供效能平台身份验证/汇总使用）。

表结构约定（唯一键 uk_biz_name = (biz_line, name)）：
  id, biz_line(中文名), name, role, employee_id, active(1=在职,0=离职), created_at, updated_at

幂等：INSERT ... ON DUPLICATE KEY UPDATE，重复同步不会产生重复数据。

用法:
  python sync_roster_to_mysql.py                 # 同步全部业务线
  python sync_roster_to_mysql.py --dry-run       # 试运行，只看不写
  python sync_roster_to_mysql.py --biz-line 效贷  # 只同步某条业务线

连接配置: 复用现有 mysql_config.json（本机私有），优先取 --config-biz-line 指定业务线的配置，
          否则按已知业务线顺序扫描 ~/.workbuddy/data/time-tracking/*/mysql_config.json。
          所有业务线共用同一 MySQL 库，任一有效配置即可。
"""

import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.isdir(os.path.join(SCRIPT_DIR, "pymysql")):
    sys.path.insert(0, SCRIPT_DIR)

from biz_line_helper import CODE_TO_BIZ_LINE_MAP, BIZ_LINE_CODE_MAP

try:
    import pymysql
    import pymysql.cursors
except ImportError:
    print("ERROR: pymysql 未打包进脚本目录。请确认 scripts/pymysql/ 存在。", file=sys.stderr)
    sys.exit(1)

HOME = os.path.expanduser("~")

# 查找 mysql_config.json 时的业务线候选顺序（优先本机已初始化过的业务线）
SCAN_BIZ_LINES = ["效贷", "泾渭云", "效融", "小贷", "智慧记+运营系统", "AI进销存", "智慧记零售"]


def get_skill_dir():
    return os.path.dirname(SCRIPT_DIR)


def load_team_roster():
    """加载花名册（config/team_roster.yaml，已弃用——人员改存 MySQL agent_team_roster 表），复用 record_time_saved 的简易解析兜底"""
    roster_path = os.path.join(get_skill_dir(), "config", "team_roster.yaml")
    if not os.path.exists(roster_path):
        print(f"ERROR: 花名册不存在: {roster_path}", file=sys.stderr)
        sys.exit(1)
    try:
        import yaml
        with open(roster_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {"members": []}
    except ImportError:
        members = []
        current = {}
        with open(roster_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip()
                stripped = line.strip()
                if stripped.startswith("- name:"):
                    if current:
                        members.append(current)
                    current = {"name": line.split(":", 1)[1].strip().strip('"')}
                elif "role:" in line and current:
                    current["role"] = line.split(":", 1)[1].strip().strip('"')
                elif "active:" in line and current:
                    current["active"] = line.split(":", 1)[1].strip().strip('"').lower() == "true"
                elif "biz_line_code:" in line and current:
                    # 解析 ["XD", "JWY"] 形式
                    val = line.split(":", 1)[1].strip()
                    codes = [c.strip().strip('"').strip("'") for c in val.strip("[]").split(",")]
                    current["biz_line_code"] = [c for c in codes if c]
            if current:
                members.append(current)
        return {"members": members}


def find_mysql_config(preferred_biz_line=""):
    """定位本机 mysql_config.json"""
    candidates = []
    if preferred_biz_line:
        candidates.append(preferred_biz_line)
    candidates += SCAN_BIZ_LINES

    seen = set()
    for biz in candidates:
        if biz in seen:
            continue
        seen.add(biz)
        p = os.path.join(HOME, ".workbuddy", "data", "time-tracking", biz, "mysql_config.json")
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
    return None


def expand_roster(members, only_biz_line=""):
    """把成员按业务线展开成 (biz_line中文名, name, role, active) 列表"""
    rows = []
    seen = set()
    for m in members:
        name = (m.get("name") or "").strip()
        role = (m.get("role") or "功能测试").strip() or "功能测试"
        active = 1 if m.get("active", True) else 0
        codes = m.get("biz_line_code") or []
        if isinstance(codes, str):
            codes = [codes]
        if not name:
            continue
        for code in codes:
            biz = CODE_TO_BIZ_LINE_MAP.get(code, "")
            if not biz:
                print(f"⚠️  跳过未知业务线编码 '{code}'（成员 {name}）", file=sys.stderr)
                continue
            if only_biz_line and biz != only_biz_line:
                continue
            key = (biz, name)
            if key in seen:
                continue
            seen.add(key)
            rows.append((biz, name, role, active))
    return rows


def upsert(conn, table, biz_line, name, role, active):
    sql = f"""
        INSERT INTO {table} (biz_line, name, role, employee_id, active)
        VALUES (%(biz_line)s, %(name)s, %(role)s, '', %(active)s)
        ON DUPLICATE KEY UPDATE
            role=VALUES(role), active=VALUES(active)
    """
    with conn.cursor() as cur:
        cur.execute(sql, {"biz_line": biz_line, "name": name, "role": role, "active": active})


def main():
    parser = argparse.ArgumentParser(description="花名册同步到 MySQL agent_team_roster 表")
    parser.add_argument("--biz-line", default="", help="只同步某条业务线（中文名），默认全部")
    parser.add_argument("--config-biz-line", default="效贷", help="读取连接配置的业务线（默认 效贷）")
    parser.add_argument("--dry-run", action="store_true", help="试运行，只看不写")
    args = parser.parse_args()

    if args.biz_line and args.biz_line not in BIZ_LINE_CODE_MAP:
        print(f"ERROR: 未知业务线 '{args.biz_line}'。支持: {', '.join(BIZ_LINE_CODE_MAP.keys())}", file=sys.stderr)
        sys.exit(1)

    roster = load_team_roster()
    rows = expand_roster(roster.get("members", []), args.biz_line)

    print("=" * 62)
    print(f"花名册同步到 MySQL (agent_team_roster)")
    print("=" * 62)
    print(f"业务线范围: {args.biz_line or '全部'}")
    print(f"待同步成员: {len(rows)} 行（业务线×成员）")

    if not rows:
        print("✅ 没有需要同步的成员。")
        return

    cfg = find_mysql_config(args.config_biz_line)
    if not cfg:
        print("ERROR: 未找到 mysql_config.json。请先运行 init_mysql_config.py 初始化。", file=sys.stderr)
        sys.exit(1)

    table = "agent_team_roster"

    if args.dry_run:
        print(f"\n🔍 试运行 — 目标 {cfg.get('host')}:{cfg.get('port')}/{cfg.get('database')}.{table}:")
        for biz, name, role, active in rows:
            print(f"  {biz:14s} | {name:8s} | {role} | active={active}")
        print(f"\n共 {len(rows)} 行（未实际写入）")
        return

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
    print(f"✅ 已连接 MySQL: {cfg.get('host')}:{cfg.get('port')}/{cfg.get('database')}.{table}")

    ok = 0
    fail = 0
    for biz, name, role, active in rows:
        try:
            upsert(conn, table, biz, name, role, active)
            ok += 1
            print(f"  ✅ {biz:14s} | {name:8s} | {role} | active={active}")
        except Exception as e:
            fail += 1
            print(f"  ❌ {biz:14s} | {name:8s} → {e}")

    conn.commit()
    conn.close()

    print("\n" + "=" * 62)
    print(f"同步完成: 成功 {ok} 行 / 失败 {fail} 行 / 合计 {len(rows)} 行")
    print("=" * 62)

    if fail > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
