#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
register_sync_tasks.py — 自动注册 time-tracking 定时同步任务（自定位 / 幂等）

设计目标（v5.8 引入，修复 v5.3 的「占位符路径不可靠」问题）：
  让「任何测试人员 / 任何机器」在首次使用内嵌本 skill 的测试专家时，
  AI 只需运行一句命令即可在本机「任务计划程序」自动建好
  09:00 / 12:00 / 18:00 三个每日任务，无需人工打开 CMD、无需模型填写绝对路径。

关键特性：
  - 自定位：用 __file__ 推断 scripts 目录，找到同目录的 sync_task.bat，
            不需要任何路径参数，彻底消除跨机器路径不确定性。
  - 幂等：已注册的任务自动跳过（不重复创建、不报错）。
  - 多业务线：任务名带业务线前缀，不同业务线互不冲突。
  - 失败友好：注册失败打印明确原因与手动命令，不阻塞 AI 其余流程。
  - 时机无关：业务线一确定即可调用，不要求 MySQL 配置已填写。
"""
import argparse
import os
import subprocess
import sys

# 早 / 午 / 晚 三个触发时间点
SCHEDULES = [
    ("早", "09:00"),
    ("午", "12:00"),
    ("晚", "18:00"),
]


def run(cmd):
    """执行命令，返回 (returncode, stdout, stderr)。schtasks 输出为 GBK，按 gbk 解码。"""
    try:
        p = subprocess.run(
            cmd, shell=True, capture_output=True,
            encoding="gbk", errors="ignore", timeout=60,
        )
        return p.returncode, p.stdout, p.stderr
    except Exception as e:  # noqa: BLE001
        return -1, "", str(e)


def task_exists(task_name):
    rc, _out, _err = run('schtasks /query /tn "%s"' % task_name)
    return rc == 0


def register_one(bat_path, biz_line, label, hhmm):
    task_name = "%s时间同步-%s" % (biz_line, label)
    if task_exists(task_name):
        return task_name, "已存在(跳过)"
    # /tr 值整体用外层双引号包裹；bat 路径内含空格需自带 \" 转义，末尾传业务线参数
    tr_value = '"\\"%s\\" %s"' % (bat_path, biz_line)
    cmd = (
        'schtasks /create /tn "%s" /tr %s /sc daily /st %s /f'
        % (task_name, tr_value, hhmm)
    )
    rc, _out, err = run(cmd)
    if rc == 0:
        return task_name, "已创建(%s)" % hhmm
    return task_name, "失败(rc=%d) %s" % (rc, err.strip()[:160])


def main():
    ap = argparse.ArgumentParser(description="注册 time-tracking 定时同步任务（自定位/幂等）")
    ap.add_argument("--biz-line", required=True, help="业务线名称，如 效贷")
    ap.add_argument("--dry-run", action="store_true", help="只检查与打印，不真正创建")
    args = ap.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    bat_path = os.path.join(script_dir, "sync_task.bat")
    if not os.path.isfile(bat_path):
        print("[ERROR] 未找到同目录的 sync_task.bat：%s" % bat_path)
        print("        请确认 register_sync_tasks.py 与 sync_task.bat 处于同一 scripts 目录。")
        return 2

    print("[INFO] scripts 目录: %s" % script_dir)
    print("[INFO] 目标 bat    : %s" % bat_path)
    print("[INFO] 业务线      : %s" % args.biz_line)
    print("[INFO] 计划注册 3 个每日任务(09:00/12:00/18:00)，已存在自动跳过...\n")

    if args.dry_run:
        for label, hhmm in SCHEDULES:
            name = "%s时间同步-%s" % (args.biz_line, label)
            state = "已存在" if task_exists(name) else ("将创建@" + hhmm)
            print("  [DRY] %s -> %s" % (name, state))
        return 0

    results = [register_one(bat_path, args.biz_line, l, t) for l, t in SCHEDULES]
    ok = 0
    for name, status in results:
        print("  %s: %s" % (name, status))
        if "已创建" in status or "已存在" in status:
            ok += 1

    print("\n[SUMMARY] %d/%d 任务就绪（早/午/晚）" % (ok, len(results)))
    if ok == len(results):
        print("[OK] 定时同步任务已就绪，无需手动操作。MySQL 配置补齐后，数据将每日自动入库。")
        return 0
    print("[WARN] 部分任务未创建成功，可能需管理员权限（schtasks 被禁用或权限不足）。")
    print("       手动备选：以管理员身份 CMD 执行：")
    print('         schtasks /create /tn "%s时间同步-早" /tr "\\"%s\\" %s" /sc daily /st 09:00 /f'
          % (args.biz_line, bat_path, args.biz_line))
    return 1


if __name__ == "__main__":
    sys.exit(main())
