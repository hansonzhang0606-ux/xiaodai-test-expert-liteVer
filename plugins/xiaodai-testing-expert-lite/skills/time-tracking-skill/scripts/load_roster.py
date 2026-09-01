#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时从 MySQL agent_team_roster 表查询在职人员花名册。

身份识别 / 业务线确认均基于此脚本输出，**不再读取 team_roster.yaml**。
team_roster.yaml 已弃用——人员由管理员直接维护在 MySQL agent_team_roster 表；运行时身份验证一律查 MySQL，保证多副本/多机器部署下花名册永远最新。

用法:
  python load_roster.py                  # 人类阅读格式
  python load_roster.py --json           # AI 解析用（推荐）
  python load_roster.py --json --biz-line 效贷    # 仅某业务线
  python load_roster.py --include-inactive         # 同时返回离职人员（仅排查用）

连接配置：扫描 ~/.workbuddy/data/time-tracking/*/mysql_config.json 任一份有效配置。
agent_team_roster 与 agent_time_tracking 共用同一 MySQL 库，连接信息相同。

退出码:
  0 - 成功
  1 - 配置缺失 / 连接失败 / 查询异常
"""

import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.isdir(os.path.join(SCRIPT_DIR, "pymysql")):
    sys.path.insert(0, SCRIPT_DIR)

from biz_line_helper import BIZ_LINE_CODE_MAP

try:
    import pymysql
    import pymysql.cursors
except ImportError:
    print("ERROR: pymysql 未打包进脚本目录。请确认 scripts/pymysql/ 存在。", file=sys.stderr)
    sys.exit(1)

HOME = os.path.expanduser("~")


def find_mysql_config():
    """扫描 ~/.workbuddy/data/time-tracking/*/mysql_config.json，找任一份有效配置"""
    for biz_line in BIZ_LINE_CODE_MAP.keys():
        p = os.path.join(HOME, ".workbuddy", "data", "time-tracking", biz_line, "mysql_config.json")
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f), p
            except Exception:
                continue
    return None, None


def load_roster_from_mysql(biz_line_filter="", include_inactive=False):
    """查 agent_team_roster，返回聚合后的 {name: {biz_line:[...], biz_line_code:[...], role, active}}"""
    cfg, cfg_path = find_mysql_config()
    if not cfg:
        raise RuntimeError(
            "MySQL 配置未初始化（~/.workbuddy/data/time-tracking/*/mysql_config.json 不存在）。"
            "请先运行 init_mysql_config.py 初始化。"
        )

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
            sql = "SELECT biz_line, name, role, active FROM agent_team_roster"
            params = []
            conditions = []
            if not include_inactive:
                conditions.append("active=1")
            if biz_line_filter:
                conditions.append("biz_line=%s")
                params.append(biz_line_filter)
            if conditions:
                sql += " WHERE " + " AND ".join(conditions)
            sql += " ORDER BY biz_line, name"
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
    finally:
        conn.close()

    result = {}
    for r in rows:
        name = r["name"]
        biz_line = r["biz_line"]
        role = r["role"]
        active = bool(r["active"])
        code = BIZ_LINE_CODE_MAP.get(biz_line, "")
        if name not in result:
            result[name] = {"biz_line": [], "biz_line_code": [], "role": role, "active": active}
        if biz_line not in result[name]["biz_line"]:
            result[name]["biz_line"].append(biz_line)
        if code and code not in result[name]["biz_line_code"]:
            result[name]["biz_line_code"].append(code)
    return result, cfg_path


def main():
    parser = argparse.ArgumentParser(description="从 MySQL agent_team_roster 查询花名册")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式（AI 解析）")
    parser.add_argument("--biz-line", default="", help="仅查询某业务线（中文名）")
    parser.add_argument("--include-inactive", action="store_true", help="包含离职人员（默认仅在职）")
    args = parser.parse_args()

    if args.biz_line and args.biz_line not in BIZ_LINE_CODE_MAP:
        print(f"ERROR: 未知业务线 '{args.biz_line}'。支持: {', '.join(BIZ_LINE_CODE_MAP.keys())}", file=sys.stderr)
        sys.exit(1)

    try:
        roster, cfg_path = load_roster_from_mysql(args.biz_line, args.include_inactive)
    except Exception as e:
        if args.json:
            print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))
        else:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        members = []
        for name, info in sorted(roster.items()):
            members.append({
                "name": name,
                "biz_line": info["biz_line"],
                "biz_line_code": info["biz_line_code"],
                "role": info["role"],
                "active": info["active"],
            })
        print(json.dumps({
            "status": "ok",
            "config_path": cfg_path,
            "total": len(members),
            "members": members,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"在职人员: {len(roster)} 人  (来源: {cfg_path})")
        for name, info in sorted(roster.items()):
            codes = ", ".join(info["biz_line_code"]) or "(未知)"
            lines = ", ".join(info["biz_line"])
            tag = "离职" if not info["active"] else "在职"
            print(f"  {name:8s} | {lines:14s} | [{codes:24s}] | {info['role']:6s} | {tag}")


if __name__ == "__main__":
    main()