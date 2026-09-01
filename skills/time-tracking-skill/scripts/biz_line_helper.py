#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
biz_line 助手 — 提供统一的默认业务线解析

所有脚本通过 --biz-line 参数显式指定业务线；
未指定时，回退读取 config/time_tracking_config.yaml 的 default_biz_line 字段。
两者都为空时报错退出，绝不猜测默认业务线。

支持的业务线编码（与 config/team_roster.yaml 对照）：
  XD:效贷  JWY:泾渭云  XR:效融  XXD:小贷
  ZHJ:智慧记+运营系统  AIJXC:AI进销存  ZHJLS:智慧记零售
（智慧记三子线为独立业务线，统一使用各自全称，不使用「智慧记」统称）
"""

import os
import re
import sys

# 业务线中文名 -> 编码
# 注意：智慧记下有三个子业务线，各用独立名称与编码：
#   ZHJ:智慧记+运营系统  AIJXC:AI进销存  ZHJLS:智慧记零售
# 「智慧记」是统称，不是业务线名，部署时 default_biz_line / --biz-line 必须填具体子业务线名。
BIZ_LINE_CODE_MAP = {
    "效贷": "XD",
    "泾渭云": "JWY",
    "效融": "XR",
    "小贷": "XXD",
    "智慧记+运营系统": "ZHJ",
    "AI进销存": "AIJXC",
    "智慧记零售": "ZHJLS",
}

# 编码 -> 中文名（反向映射，供 AI 在多业务线编号选项展示时反查名称）
CODE_TO_BIZ_LINE_MAP = {v: k for k, v in BIZ_LINE_CODE_MAP.items()}


def code_to_biz_line(code: str) -> str:
    """业务线编码转中文名，未知编码返回空字符串"""
    return CODE_TO_BIZ_LINE_MAP.get(code, "")


def get_skill_dir() -> str:
    """获取 skill 根目录（本文件位于 scripts/ 下）"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_default_biz_line() -> str:
    """从 config/time_tracking_config.yaml 读取 default_biz_line（简易扫描，无 PyYAML 依赖）"""
    cfg_path = os.path.join(get_skill_dir(), "config", "time_tracking_config.yaml")
    if not os.path.exists(cfg_path):
        return ""
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^\s*default_biz_line\s*:\s*[\"']?([^\"'#\n]+)", line)
                if m:
                    return m.group(1).strip()
    except Exception:
        pass
    return ""


def resolve_biz_line(cli_value: str) -> str:
    """解析业务线：CLI 参数优先，其次配置文件 default_biz_line，都为空则报错退出"""
    biz_line = (cli_value or "").strip() or get_default_biz_line()
    if not biz_line:
        print("ERROR: 未指定业务线。请通过 --biz-line 参数指定，", file=sys.stderr)
        print("       或在 config/time_tracking_config.yaml 中设置 default_biz_line。", file=sys.stderr)
        print(f"       支持的业务线: {', '.join(BIZ_LINE_CODE_MAP.keys())}", file=sys.stderr)
        sys.exit(1)
    return biz_line


def biz_line_to_code(biz_line: str) -> str:
    """业务线中文名转编码，未知业务线返回空字符串"""
    return BIZ_LINE_CODE_MAP.get(biz_line, "")
