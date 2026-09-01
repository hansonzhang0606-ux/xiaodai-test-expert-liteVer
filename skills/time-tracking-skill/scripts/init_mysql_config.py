#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
初始化 MySQL 本地配置文件（多业务线通用版，支持 AI 自动模式）

此脚本不打包任何真实凭据，安装 skill 后由测试人员在自己电脑上运行一次，
生成本机专用的 mysql_config.json，供后续 sync_to_mysql.py 定时同步使用。

v1.5.1 起支持 AI 自动模式（WorkBuddy/IDE 会话启动时由 AI 自动调用，测试人员无需开 CMD）：
  python init_mysql_config.py --biz-line 智慧记+运营系统 --auto --password "xxx" --no-interactive --quiet
  - 配置已存在 → 输出 {"status":"skipped"}（退出码 0），AI 安全跳过
  - 配置不存在 → 生成配置 → 输出 {"status":"ok"}（退出码 0）
  - 参数缺失/密码错误 → 输出 {"status":"error"}（退出码 1）

用法:
  # 交互模式（人工使用，推荐首次）
  python init_mysql_config.py --biz-line 智慧记+运营系统

  # 非交互模式（脚本/自动化调用）
  python init_mysql_config.py --biz-line 智慧记+运营系统 --password "xxx" --no-interactive --employee "张三"

  # AI 自动模式（会话启动检查时调用）：已存在则跳过，不存在则按默认生成
  python init_mysql_config.py --biz-line 智慧记+运营系统 --auto --password "xxx" --no-interactive --quiet

  # 模板模式（v1.5.3，AI 自动生成全空配置模板并生成 mysql_config.notes.md 备注说明，
  # 测试人员按备注填全部字段或找管理员获取，不在对话中索要密码）：
  python init_mysql_config.py --biz-line 智慧记+运营系统 --template --no-interactive --quiet
"""

import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from biz_line_helper import resolve_biz_line, biz_line_to_code

HOME = os.path.expanduser("~")

# 预置业务线默认数据库配置（仅默认连接信息，密码绝不写入任何文件）
# 各团队部署时按需修改/扩展此映射；未列出的业务线使用通用 localhost 默认值
DEFAULT_DB_CONFIG = {
    "效贷": {
        "host": "127.0.0.1",
        "port": 3306,
        "user": "root",
        "database": "your_database",
        "table": "agent_time_tracking",
    }
}


def get_data_dir(biz_line):
    return os.path.join(HOME, ".workbuddy", "data", "time-tracking", biz_line)


def prompt_with_default(label, default, hide=False):
    """交互式提示，带默认值；hide=True 时不回显输入"""
    if hide:
        try:
            import getpass
            value = getpass.getpass(f"{label} [{default}]: ").strip()
        except Exception:
            value = input(f"{label} [{default}]: ").strip()
    else:
        value = input(f"{label} [{default}]: ").strip()
    return value if value else default


def print_machine_result(status, message, cfg_path="", biz_line=""):
    """输出机器可读的结果（AI 可解析的 JSON，status: ok / skipped / error）"""
    result = {
        "status": status,
        "message": message,
        "config_path": cfg_path,
        "biz_line": biz_line,
        "biz_line_code": biz_line_to_code(biz_line) if biz_line else "",
    }
    print(json.dumps(result, ensure_ascii=False))


def build_config_notes(biz_line):
    """生成 mysql_config.notes.md 内容：逐字段说明取值来源，测试人员按此填写或找管理员获取。"""
    return f"""# MySQL 配置填写说明（mysql_config.json）

本文件由 AI 自动生成，所有字段初始为空。请按下方说明逐条填写，
不清楚的字段**找管理员获取**（不要自己猜，也不要发到群里 / 提交 Git）。
填写完成后，回到对话回复「已填好」即可继续。

| 字段 | 含义 | 填写说明 / 获取方式 |
|------|------|--------------------|
| host | MySQL 服务器地址 | 找管理员获取（如 db.example.internal） |
| port | 端口 | 通常 3306 |
| user | 用户名 | 找管理员获取（如 root） |
| password | 密码 | 管理员单独告知，**仅填在本机文件，不要外传** |
| database | 数据库名 | 找管理员获取（如 team_database） |
| table | 表名 | 时间记录表：agent_time_tracking；花名册表：agent_team_roster |
| charset | 字符集 | 填 utf8mb4 |
| biz_line | 业务线中文名 | 如 效贷 / 智慧记+运营系统 / AI进销存 / 智慧记零售 |
| biz_line_code | 业务线编码 | 如 XD / ZHJ / AIJXC / ZHJLS（与 biz_line 对应，找管理员确认） |

> 当前业务线：{biz_line}。agent_team_roster 与 agent_time_tracking 共用同一库，连接信息相同。
"""

def main():
    parser = argparse.ArgumentParser(description="初始化 MySQL 本地配置文件（多业务线通用版）")
    parser.add_argument("--biz-line", default="", help="业务线（未指定时读取 config 中 default_biz_line）")
    parser.add_argument("--biz-line-code", help="业务线编码（默认自动映射）")
    parser.add_argument("--host", help="MySQL 主机")
    parser.add_argument("--port", type=int, help="MySQL 端口")
    parser.add_argument("--user", help="MySQL 用户名")
    parser.add_argument("--password", default=None, help="MySQL 密码（命令行直接传不安全，仅 CI/AI 自动化场景使用）")
    parser.add_argument("--database", help="数据库名")
    parser.add_argument("--table", help="表名")
    parser.add_argument("--employee", help="当前使用者姓名（仅用于日志/标识，不写入配置）")
    parser.add_argument("--no-interactive", action="store_true", help="非交互模式，必须命令行传齐所有参数")
    parser.add_argument("--auto", action="store_true",
                        help="自动模式：配置已存在则直接跳过（退出码0，输出 status=skipped），不存在则生成")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的配置文件")
    parser.add_argument("--quiet", action="store_true", help="静默模式，只输出机器可读 JSON")
    parser.add_argument("--template", action="store_true", help="生成配置模板：全部字段留空（host/port/user/password/database/table/charset/biz_line/biz_line_code 均为空）并生成 mysql_config.notes.md 备注说明；测试人员按备注填或找管理员获取（AI 自动生成，不在对话中索要密码，代码不含任何凭据）")
    args = parser.parse_args()

    biz_line = resolve_biz_line(args.biz_line)
    defaults = DEFAULT_DB_CONFIG.get(biz_line, {
        "host": "127.0.0.1",
        "port": 3306,
        "user": "root",
        "database": "your_database",
        "table": "agent_time_tracking",
    })

    data_dir = get_data_dir(biz_line)
    os.makedirs(data_dir, exist_ok=True)
    cfg_path = os.path.join(data_dir, "mysql_config.json")

    # 自动模式：已存在则跳过（退出码 0，避免 AI 误判为失败）
    if args.auto and os.path.exists(cfg_path) and not args.force:
        msg = f"配置文件已存在: {cfg_path}，无需重复初始化。"
        if args.quiet:
            print_machine_result("skipped", msg, cfg_path=cfg_path, biz_line=biz_line)
        else:
            print(f"✅ {msg}")
        return 0

    # 普通模式：已存在则提示，但 --force 可覆盖
    if os.path.exists(cfg_path) and not args.force:
        msg = f"配置文件已存在: {cfg_path}。如需重新生成，请删除该文件或加 --force 参数覆盖。"
        if args.quiet:
            print_machine_result("skipped", msg, cfg_path=cfg_path, biz_line=biz_line)
        else:
            print(f"⚠️  {msg}", file=sys.stderr)
        return 0  # 退出码 0，避免 AI 调用时误判为失败

    # 模板模式（v1.5.3）：生成全空配置模板 + 备注说明文件，AI 自动调用，不在对话中索要密码
    if args.template:
        cfg_dir = os.path.dirname(cfg_path)
        os.makedirs(cfg_dir, exist_ok=True)
        config = {
            "host": "",
            "port": "",
            "user": "",
            "password": "",
            "database": "",
            "table": "",
            "charset": "",
            "biz_line": "",
            "biz_line_code": "",
        }
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        notes_path = os.path.join(cfg_dir, "mysql_config.notes.md")
        with open(notes_path, "w", encoding="utf-8") as nf:
            nf.write(build_config_notes(biz_line))
        msg = f"配置模板已生成(请按 mysql_config.notes.md 备注填写全部字段): {cfg_path}"
        if args.quiet:
            print_machine_result("ok", msg, cfg_path=cfg_path, biz_line=biz_line)
        else:
            print(f"✅ {msg}")
        return 0

    if args.no_interactive:
        if not args.password:
            msg = "ERROR: --no-interactive 模式下必须提供 --password"
            if args.quiet:
                print_machine_result("error", msg, cfg_path=cfg_path, biz_line=biz_line)
            else:
                print(msg, file=sys.stderr)
            return 1
        config = {
            "host": args.host or defaults["host"],
            "port": args.port or defaults["port"],
            "user": args.user or defaults["user"],
            "password": args.password,
            "database": args.database or defaults["database"],
            "table": args.table or defaults["table"],
            "charset": "utf8mb4",
            "biz_line": biz_line,
            "biz_line_code": args.biz_line_code or biz_line_to_code(biz_line),
        }
    else:
        print("=" * 60)
        print(f"初始化 {biz_line} 业务线 MySQL 本地配置")
        print("=" * 60)
        print(f"配置文件将保存到: {cfg_path}")
        if args.employee:
            print(f"当前使用者: {args.employee}")
        print("提示：密码仅保存在本机，不会随专家包上传或分发。\n")

        config = {
            "host": prompt_with_default("主机", args.host or defaults["host"]),
            "port": int(prompt_with_default("端口", str(args.port or defaults["port"]))),
            "user": prompt_with_default("用户名", args.user or defaults["user"]),
            "password": prompt_with_default("密码", args.password or "", hide=True),
            "database": prompt_with_default("数据库", args.database or defaults["database"]),
            "table": prompt_with_default("表名", args.table or defaults["table"]),
            "charset": "utf8mb4",
            "biz_line": biz_line,
            "biz_line_code": args.biz_line_code or biz_line_to_code(biz_line),
        }

    if not config["password"]:
        msg = "ERROR: 密码不能为空"
        if args.quiet:
            print_machine_result("error", msg, cfg_path=cfg_path, biz_line=biz_line)
        else:
            print(msg, file=sys.stderr)
        return 1

    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    msg = f"配置文件已生成: {cfg_path}"
    if args.quiet:
        print_machine_result("ok", msg, cfg_path=cfg_path, biz_line=biz_line)
    else:
        print(f"\n✅ {msg}")
        print("   后续可直接运行: python sync_to_mysql.py --biz-line " + biz_line)
        if args.employee:
            print(f"   员工: {args.employee}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
