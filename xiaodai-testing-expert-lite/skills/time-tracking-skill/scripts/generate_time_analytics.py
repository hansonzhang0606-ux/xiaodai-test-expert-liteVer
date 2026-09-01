#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
时间节省分析报告生成脚本（通用多业务线版）
读取 records.jsonl，生成 HTML 可视化分析报告。

用法:
  python generate_time_analytics.py                          # 使用 config 中 default_biz_line 生成报告（全量）
  python generate_time_analytics.py --biz-line "智慧记+运营系统"      # 指定业务线
  python generate_time_analytics.py --person "张三"           # 生成个人视角报告（该员工所有历史记录）
  python generate_time_analytics.py --output report.html     # 指定输出路径
  python generate_time_analytics.py --format csv             # 输出 CSV 格式

输出:
  - HTML 报告（默认）：包含总览、按员工/故事/步骤三个维度的统计图表 + JS 筛选面板
  - CSV 报告：原始数据 + 汇总表
  - 个人报告：预过滤为指定员工的所有历史记录（跨所有故事、所有步骤），标题统一为"{biz_line}测试时间节省报告"
  - 业务线报告：默认全量，显示所有测试人员的节省数据
"""

import argparse
import json
import os
import sys
from datetime import datetime
from collections import defaultdict


HOURS_PER_PD = 8.0
STEP_ORDER = ["01", "02", "04", "06", "07"]
STEP_NAMES = {
    "01": "文档整理",
    "02": "需求评审",
    "04": "生成测试点",
    "06": "用例细化",
    "07": "知识入库",
}
# 兼容旧数据中使用的步骤名称别名
STEP_NAME_ALIASES = {
    "生成用例": "用例细化",
    "入库知识库": "知识入库",
}


def get_data_dir(biz_line: str) -> str:
    home = os.path.expanduser("~")
    return os.path.join(home, ".workbuddy", "data", "time-tracking", biz_line)


def get_records_path(biz_line: str) -> str:
    return os.path.join(get_data_dir(biz_line), "records.jsonl")


def load_records(biz_line: str, input_path: str = None) -> list:
    """加载所有记录

    Args:
        biz_line: 业务线名称（用于本地 records.jsonl）
        input_path: 外部数据文件路径（JSON 或 Excel），优先使用
    """
    # 优先从外部文件读取
    if input_path and os.path.exists(input_path):
        # Excel 文件
        if input_path.lower().endswith((".xlsx", ".xls")):
            try:
                # 尝试导入同目录的 sync_to_excel
                script_dir = os.path.dirname(os.path.abspath(__file__))
                if script_dir not in sys.path:
                    sys.path.insert(0, script_dir)
                from sync_to_excel import read_excel_to_json
                records = read_excel_to_json(input_path)
                print(f"从 Excel 读取 {len(records)} 条记录: {input_path}", file=sys.stderr)
                return records
            except ImportError:
                print(f"错误: 无法导入 sync_to_excel 模块，请确保在同一目录", file=sys.stderr)
                return []

        # JSON 文件
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "records" in data:
            return data["records"]
        else:
            return [data]

    # 从本地 records.jsonl 读取
    path = get_records_path(biz_line)
    if not os.path.exists(path):
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def generate_csv(records: list, biz_line: str, output_path: str):
    """生成 CSV 报告"""
    import csv
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "时间", "日期", "业务线", "员工", "用户故事",
            "步骤", "步骤代码", "节省小时", "节省人天", "备注"
        ])
        for r in records:
            writer.writerow([
                r.get("timestamp", ""),
                r.get("date", ""),
                r.get("biz_line", ""),
                r.get("employee", ""),
                r.get("user_story", ""),
                r.get("step", ""),
                r.get("step_code", ""),
                r.get("time_saved_hours", 0),
                r.get("time_saved_pd", 0),
                r.get("remark", ""),
            ])
    print(f"CSV 报告已生成: {output_path}")


def compute_stats(records: list) -> dict:
    """计算统计数据"""
    total_records = len(records)
    total_hours = sum(r.get("total_hours", r.get("time_saved_hours", 0)) for r in records)
    total_pd = sum(r.get("time_saved_pd", 0) for r in records)

    by_employee = defaultdict(lambda: {"hours": 0, "pd": 0, "count": 0, "stories": set()})
    by_story = defaultdict(lambda: {"hours": 0, "pd": 0, "count": 0, "employees": set(), "steps": set()})
    by_step = defaultdict(lambda: {"hours": 0, "pd": 0, "count": 0, "employees": set()})
    by_date = defaultdict(lambda: {"hours": 0, "pd": 0, "count": 0})
    cross_data = defaultdict(lambda: defaultdict(float))

    for r in records:
        emp = r.get("employee", "未知")
        story = r.get("user_story", "未知")
        step = r.get("step", "未知")
        date = r.get("date", "未知")
        hours = r.get("total_hours", r.get("time_saved_hours", 0))
        pd = r.get("time_saved_pd", 0)

        by_employee[emp]["hours"] += hours
        by_employee[emp]["pd"] += pd
        by_employee[emp]["count"] += 1
        by_employee[emp]["stories"].add(story)

        by_story[story]["hours"] += hours
        by_story[story]["pd"] += pd
        by_story[story]["count"] += 1
        by_story[story]["employees"].add(emp)
        by_story[story]["steps"].add(step)

        by_step[step]["hours"] += hours
        by_step[step]["pd"] += pd
        by_step[step]["count"] += 1
        by_step[step]["employees"].add(emp)

        by_date[date]["hours"] += hours
        by_date[date]["pd"] += pd
        by_date[date]["count"] += 1

        cross_data[emp][step] += hours / HOURS_PER_PD

    # 将 set 转为 list 以便 JSON 序列化
    by_employee_out = {}
    for emp, v in by_employee.items():
        by_employee_out[emp] = {**v, "stories": sorted(v["stories"])}

    by_story_out = {}
    for story, v in by_story.items():
        by_story_out[story] = {**v, "employees": sorted(v["employees"]), "steps": sorted(v["steps"])}

    by_step_out = {}
    for step, v in by_step.items():
        by_step_out[step] = {**v, "employees": sorted(v["employees"])}

    return {
        "total_records": total_records,
        "total_hours": total_hours,
        "total_pd": total_pd,
        "by_employee": by_employee_out,
        "by_story": by_story_out,
        "by_step": by_step_out,
        "by_date": dict(by_date),
        "cross_data": {emp: dict(steps) for emp, steps in cross_data.items()},
        "unique_employees": len(by_employee),
        "unique_stories": len(by_story),
    }


def generate_html(records: list, biz_line: str, output_path: str, person_name: str = ""):
    """生成 HTML 可视化报告

    Args:
        records: 时间节省记录列表
        biz_line: 业务线名称
        output_path: 输出文件路径
        person_name: 个人报告模式下的员工姓名，为空则为全业务线报告
    """
    report_title = f"{biz_line}测试时间节省报告" if biz_line else "测试时间节省报告"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    report_subtitle = f"个人历史累计 · 所有用户故事 · 所有步骤 · 报告时间 {now}" if person_name else f"全业务线汇总 · 所有测试人员 · 报告时间 {now}"

    stats = compute_stats(records)

    # 所有员工、步骤、故事、日期（用于下拉选项）
    all_employees = sorted(set(r.get("employee", "未知") for r in records))
    all_steps = sorted(set(r.get("step", "未知") for r in records))
    all_stories = sorted(set(r.get("user_story", "未知") for r in records))
    all_dates = sorted(set(r.get("date", "") for r in records if r.get("date")))

    # 步骤排序：按 STEP_ORDER 顺序，同时兼容旧名称别名
    def step_sort_key(s):
        canonical = STEP_NAME_ALIASES.get(s, s)
        for code, name in STEP_NAMES.items():
            if name == canonical:
                return STEP_ORDER.index(code)
        return 99

    all_steps = sorted(all_steps, key=step_sort_key)
    steps_sorted = sorted(stats["by_step"].keys(), key=step_sort_key)
    employees_sorted = sorted(stats["by_employee"].keys())

    # 最大值用于柱状图比例
    max_emp_hours = max((v["hours"] for v in stats["by_employee"].values()), default=1)
    max_step_hours = max((v["hours"] for v in stats["by_step"].values()), default=1)
    max_story_hours = max((v["hours"] for v in stats["by_story"].values()), default=1)
    max_date_hours = max((v["hours"] for v in stats["by_date"].values()), default=1)

    records_json = json.dumps(records, ensure_ascii=False)
    stats_json = json.dumps(stats, ensure_ascii=False)

    # 生成初始表格行 HTML
    def employee_rows(s):
        rows = []
        max_h = max((v["hours"] for v in s["by_employee"].values()), default=1)
        for emp in sorted(s["by_employee"].keys(), key=lambda e: s["by_employee"][e]["hours"], reverse=True):
            v = s["by_employee"][emp]
            bar_width = int(v["hours"] / max_h * 100) if max_h > 0 else 0
            rows.append(f"""
      <tr>
        <td class="number">{emp}</td>
        <td>{v['pd']:.1f} 人天 ({v['hours']:.1f} 小时)</td>
        <td><span class="bar-container"><span class="bar green" style="width: {bar_width}%"></span></span></td>
        <td>{v['count']}</td>
        <td>{len(v['stories'])}</td>
      </tr>""")
        return "\n".join(rows)

    def step_rows(s):
        rows = []
        max_h = max((v["hours"] for v in s["by_step"].values()), default=1)
        step_order_sorted = sorted(s["by_step"].keys(), key=step_sort_key)
        for step in step_order_sorted:
            v = s["by_step"][step]
            bar_width = int(v["hours"] / max_h * 100) if max_h > 0 else 0
            rows.append(f"""
      <tr>
        <td class="number">{step}</td>
        <td>{v['pd']:.1f} 人天 ({v['hours']:.1f} 小时)</td>
        <td><span class="bar-container"><span class="bar blue" style="width: {bar_width}%"></span></span></td>
        <td>{v['count']}</td>
        <td>{len(v['employees'])}</td>
      </tr>""")
        return "\n".join(rows)

    def story_rows(s):
        rows = []
        max_h = max((v["hours"] for v in s["by_story"].values()), default=1)
        for story in sorted(s["by_story"].keys(), key=lambda s2: s["by_story"][s2]["hours"], reverse=True):
            v = s["by_story"][story]
            bar_width = int(v["hours"] / max_h * 100) if max_h > 0 else 0
            emp_tags = " ".join(f'<span class="tag b">{e}</span>' for e in sorted(v["employees"]))
            step_tags = " ".join(f'<span class="tag o">{s2}</span>' for s2 in sorted(v["steps"]))
            rows.append(f"""
      <tr>
        <td class="number">{story}</td>
        <td>{v['pd']:.1f} 人天 ({v['hours']:.1f} 小时)</td>
        <td><span class="bar-container"><span class="bar orange" style="width: {bar_width}%"></span></span></td>
        <td>{v['count']}</td>
        <td>{emp_tags}</td>
        <td>{step_tags}</td>
      </tr>""")
        return "\n".join(rows)

    def date_rows(s):
        rows = []
        max_h = max((v["hours"] for v in s["by_date"].values()), default=1)
        for date in sorted(s["by_date"].keys()):
            v = s["by_date"][date]
            bar_width = int(v["hours"] / max_h * 100) if max_h > 0 else 0
            rows.append(f"""
      <tr>
        <td class="number">{date}</td>
        <td>{v['pd']:.1f} 人天 ({v['hours']:.1f} 小时)</td>
        <td><span class="bar-container"><span class="bar purple" style="width: {bar_width}%"></span></span></td>
        <td>{v['count']}</td>
      </tr>""")
        return "\n".join(rows)

    def cross_rows(s):
        rows = []
        emps = sorted(s["by_employee"].keys())
        steps = sorted(s["by_step"].keys(), key=step_sort_key)
        for emp in emps:
            row_total = sum(s["cross_data"].get(emp, {}).values())
            cells = "\n".join(
                f"        <td>{s['cross_data'].get(emp, {}).get(step, 0):.1f}</td>" if s['cross_data'].get(emp, {}).get(step, 0) > 0 else "        <td>-</td>"
                for step in steps
            )
            rows.append(f"""      <tr>
        <td class='number'>{emp}</td>
{cells}
        <td class='number'>{row_total:.1f}</td>
      </tr>""")
        return "\n".join(rows)

    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{report_title}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; background: #f5f7fa; color: #333; padding: 24px; }}
  .header {{ text-align: center; margin-bottom: 24px; }}
  .header h1 {{ font-size: 28px; color: #1a1a2e; margin-bottom: 8px; }}
  .header .subtitle {{ font-size: 14px; color: #888; }}
  .summary-cards {{ display: flex; gap: 16px; margin-bottom: 32px; flex-wrap: wrap; }}
  .card {{ background: #fff; border-radius: 12px; padding: 24px; flex: 1; min-width: 200px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
  .card .label {{ font-size: 13px; color: #888; margin-bottom: 8px; }}
  .card .value {{ font-size: 32px; font-weight: 700; }}
  .card .unit {{ font-size: 14px; color: #aaa; margin-left: 4px; }}
  .card.green .value {{ color: #00a870; }}
  .card.blue .value {{ color: #1890ff; }}
  .card.orange .value {{ color: #fa8c16; }}
  .card.purple .value {{ color: #722ed1; }}
  .section {{ background: #fff; border-radius: 12px; padding: 24px; margin-bottom: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
  .section h2 {{ font-size: 18px; color: #1a1a2e; margin-bottom: 16px; border-left: 4px solid #00a870; padding-left: 12px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  th {{ background: #fafafa; text-align: left; padding: 10px 12px; border-bottom: 2px solid #f0f0f0; font-weight: 600; color: #555; }}
  td {{ padding: 10px 12px; border-bottom: 1px solid #f0f0f0; }}
  tr:hover td {{ background: #fafafa; }}
  .bar-container {{ display: inline-block; width: 200px; height: 20px; background: #f0f0f0; border-radius: 10px; overflow: hidden; vertical-align: middle; margin-right: 8px; }}
  .bar {{ height: 100%; border-radius: 10px; transition: width 0.5s ease; }}
  .bar.green {{ background: linear-gradient(90deg, #00a870, #36cfc9); }}
  .bar.blue {{ background: linear-gradient(90deg, #1890ff, #69b1ff); }}
  .bar.orange {{ background: linear-gradient(90deg, #fa8c16, #ffc069); }}
  .bar.purple {{ background: linear-gradient(90deg, #722ed1, #9254de); }}
  .number {{ font-weight: 600; color: #1a1a2e; }}
  .tag {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin: 1px; }}
  .tag.g {{ background: #f6ffed; color: #52c41a; border: 1px solid #b7eb8f; }}
  .tag.b {{ background: #e6f7ff; color: #1890ff; border: 1px solid #91d5ff; }}
  .tag.o {{ background: #fff7e6; color: #fa8c16; border: 1px solid #ffd591; }}
  .empty {{ text-align: center; padding: 48px; color: #999; font-size: 16px; }}
  .footer {{ text-align: center; margin-top: 32px; color: #aaa; font-size: 12px; }}
  .cross-table th, .cross-table td {{ text-align: center; font-size: 13px; }}
  .cross-table th:first-child, .cross-table td:first-child {{ text-align: left; }}

  /* 筛选面板样式 */
  .filter-panel {{ background: #fff; border-radius: 12px; padding: 20px 24px; margin-bottom: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
  .filter-panel h2 {{ font-size: 16px; color: #1a1a2e; margin-bottom: 16px; border-left: 4px solid #1890ff; padding-left: 12px; }}
  .filter-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; align-items: end; }}
  .filter-item {{ display: flex; flex-direction: column; gap: 6px; }}
  .filter-item label {{ font-size: 13px; color: #555; font-weight: 500; }}
  .filter-item input, .filter-item select {{ padding: 8px 12px; border: 1px solid #d9d9d9; border-radius: 8px; font-size: 14px; outline: none; transition: border-color 0.2s; }}
  .filter-item input:focus, .filter-item select:focus {{ border-color: #1890ff; }}
  .filter-actions {{ display: flex; gap: 12px; margin-top: 16px; }}
  .filter-actions button {{ padding: 8px 20px; border-radius: 8px; border: none; font-size: 14px; cursor: pointer; transition: opacity 0.2s; }}
  .filter-actions button:hover {{ opacity: 0.85; }}
  .btn-primary {{ background: #1890ff; color: #fff; }}
  .btn-default {{ background: #f0f0f0; color: #555; border: 1px solid #d9d9d9 !important; }}
  .filter-status {{ margin-top: 12px; font-size: 13px; color: #888; }}
  .filter-status strong {{ color: #1890ff; }}
  .hidden-section {{ display: none; }}
</style>
</head>
<body>

<div class="header">
  <h1>{report_title}</h1>
  <div class="subtitle">{report_subtitle}</div>
</div>

<div class="filter-panel">
  <h2>筛选查询</h2>
  <div class="filter-grid">
    <div class="filter-item">
      <label for="filter-global">全局查询</label>
      <input type="text" id="filter-global" placeholder="员工 / 步骤 / 用户故事 / 备注">
    </div>
    <div class="filter-item">
      <label for="filter-employee">员工</label>
      <select id="filter-employee">
        <option value="">全部员工</option>
        {''.join(f'<option value="{e}">{e}</option>' for e in all_employees)}
      </select>
    </div>
    <div class="filter-item">
      <label for="filter-step">工作流步骤</label>
      <select id="filter-step">
        <option value="">全部步骤</option>
        {''.join(f'<option value="{s}">{s}</option>' for s in all_steps)}
      </select>
    </div>
    <div class="filter-item">
      <label for="filter-date-type">日期维度</label>
      <select id="filter-date-type">
        <option value="">全部日期</option>
        <option value="month">按月度</option>
        <option value="quarter">按季度</option>
        <option value="year">按年度</option>
      </select>
    </div>
    <div class="filter-item">
      <label for="filter-date-value">日期值</label>
      <select id="filter-date-value" disabled>
        <option value="">请先选择日期维度</option>
      </select>
    </div>
    <div class="filter-item">
      <label for="filter-story">用户故事名称（模糊查询）</label>
      <input type="text" id="filter-story" placeholder="输入用户故事名称关键词">
    </div>
  </div>
  <div class="filter-actions">
    <button class="btn-primary" onclick="applyFilters()">查询</button>
    <button class="btn-default" onclick="resetFilters()">重置</button>
  </div>
  <div class="filter-status" id="filter-status"></div>
</div>

<div class="summary-cards" id="summary-cards">
  <div class="card green">
    <div class="label">累计节省时间</div>
    <div class="value" id="total-pd">{stats['total_pd']:.1f}<span class="unit">人天</span></div>
  </div>
  <div class="card blue">
    <div class="label">折合小时</div>
    <div class="value" id="total-hours">{stats['total_hours']:.1f}<span class="unit">小时</span></div>
  </div>
  <div class="card orange">
    <div class="label">记录总数</div>
    <div class="value" id="total-records">{stats['total_records']}<span class="unit">条</span></div>
  </div>
  <div class="card purple">
    <div class="label">参与员工 / 覆盖故事</div>
    <div class="value" id="total-unique">{stats['unique_employees']}<span class="unit">人</span> / {stats['unique_stories']}<span class="unit">个故事</span></div>
  </div>
</div>

<div id="empty-tip" class="empty hidden-section">暂无符合条件的时间节省记录<br><br>请调整筛选条件后重新查询。</div>

<div id="report-content">
  <div class="section">
    <h2>按员工统计</h2>
    <table>
      <thead>
        <tr>
          <th>员工</th>
          <th>节省时间</th>
          <th>分布</th>
          <th>记录数</th>
          <th>参与故事数</th>
        </tr>
      </thead>
      <tbody id="employee-tbody">
        {employee_rows(stats)}
      </tbody>
    </table>
  </div>

  <div class="section">
    <h2>按工作流步骤统计</h2>
    <table>
      <thead>
        <tr>
          <th>步骤</th>
          <th>节省时间</th>
          <th>分布</th>
          <th>记录数</th>
          <th>参与员工数</th>
        </tr>
      </thead>
      <tbody id="step-tbody">
        {step_rows(stats)}
      </tbody>
    </table>
  </div>

  <div class="section">
    <h2>按用户故事统计</h2>
    <table>
      <thead>
        <tr>
          <th>用户故事</th>
          <th>节省时间</th>
          <th>分布</th>
          <th>记录数</th>
          <th>参与员工</th>
          <th>覆盖步骤</th>
        </tr>
      </thead>
      <tbody id="story-tbody">
        {story_rows(stats)}
      </tbody>
    </table>
  </div>

  <div class="section">
    <h2>按日期趋势</h2>
    <table>
      <thead>
        <tr>
          <th>日期</th>
          <th>节省时间</th>
          <th>分布</th>
          <th>记录数</th>
        </tr>
      </thead>
      <tbody id="date-tbody">
        {date_rows(stats)}
      </tbody>
    </table>
  </div>

  <div class="section">
    <h2>员工 x 步骤 交叉分析（单位：人天）</h2>
    <table class="cross-table">
      <thead>
        <tr>
          <th>员工</th>
          {''.join(f'<th>{step}</th>' for step in steps_sorted)}
          <th>合计</th>
        </tr>
      </thead>
      <tbody id="cross-tbody">
        {cross_rows(stats)}
      </tbody>
    </table>
  </div>
</div>

<div class="footer">
  时间节省分析报告（{biz_line}） | 由 generate_time_analytics.py 自动生成 | {now}
</div>

<script>
const ALL_RECORDS = {records_json};
const HOURS_PER_PD = {HOURS_PER_PD};
const STEP_ORDER = {json.dumps(STEP_ORDER)};
const STEP_NAMES = {json.dumps(STEP_NAMES, ensure_ascii=False)};
const STEP_NAME_ALIASES = {json.dumps(STEP_NAME_ALIASES, ensure_ascii=False)};

// 为每条记录解析日期维度
function parseRecordDate(r) {{
  const dateStr = r.date || "";
  const parts = dateStr.split("-");
  r._year = parts[0] || "";
  r._month = parts[1] || "";
  r._yearMonth = parts.length >= 2 ? `${{parts[0]}}-${{parts[1]}}` : "";
  if (r._year && r._month) {{
    const m = parseInt(r._month, 10);
    r._quarter = "Q" + (Math.ceil(m / 3));
    r._yearQuarter = `${{r._year}}-${{r._quarter}}`;
  }} else {{
    r._quarter = "";
    r._yearQuarter = "";
  }}
}}
ALL_RECORDS.forEach(parseRecordDate);

function stepSortKey(s) {{
  const canonical = STEP_NAME_ALIASES[s] || s;
  for (const [code, name] of Object.entries(STEP_NAMES)) {{
    if (name === canonical) return STEP_ORDER.indexOf(code);
  }}
  return 99;
}}

function computeStats(records) {{
  const totalRecords = records.length;
  let totalHours = 0;
  let totalPd = 0;
  const byEmployee = {{}};
  const byStory = {{}};
  const byStep = {{}};
  const byDate = {{}};
  const crossData = {{}};

  function getEmp(emp) {{
    if (!byEmployee[emp]) byEmployee[emp] = {{ hours: 0, pd: 0, count: 0, stories: new Set() }};
    return byEmployee[emp];
  }}
  function getStory(story) {{
    if (!byStory[story]) byStory[story] = {{ hours: 0, pd: 0, count: 0, employees: new Set(), steps: new Set() }};
    return byStory[story];
  }}
  function getStep(step) {{
    if (!byStep[step]) byStep[step] = {{ hours: 0, pd: 0, count: 0, employees: new Set() }};
    return byStep[step];
  }}
  function getDate(date) {{
    if (!byDate[date]) byDate[date] = {{ hours: 0, pd: 0, count: 0 }};
    return byDate[date];
  }}

  for (const r of records) {{
    const emp = r.employee || "未知";
    const story = r.user_story || "未知";
    const step = r.step || "未知";
    const date = r.date || "未知";
    const hours = r.total_hours !== undefined ? r.total_hours : (r.time_saved_hours || 0);
    const pd = r.time_saved_pd || 0;

    totalHours += hours;
    totalPd += pd;

    const e = getEmp(emp);
    e.hours += hours;
    e.pd += pd;
    e.count += 1;
    e.stories.add(story);

    const st = getStory(story);
    st.hours += hours;
    st.pd += pd;
    st.count += 1;
    st.employees.add(emp);
    st.steps.add(step);

    const sp = getStep(step);
    sp.hours += hours;
    sp.pd += pd;
    sp.count += 1;
    sp.employees.add(emp);

    const d = getDate(date);
    d.hours += hours;
    d.pd += pd;
    d.count += 1;

    if (!crossData[emp]) crossData[emp] = {{}};
    if (!crossData[emp][step]) crossData[emp][step] = 0;
    crossData[emp][step] += hours / HOURS_PER_PD;
  }}

  // 将 Set 转成 array
  const byEmployeeOut = {{}};
  for (const [k, v] of Object.entries(byEmployee)) {{
    byEmployeeOut[k] = {{ hours: v.hours, pd: v.pd, count: v.count, stories: Array.from(v.stories).sort() }};
  }}
  const byStoryOut = {{}};
  for (const [k, v] of Object.entries(byStory)) {{
    byStoryOut[k] = {{ hours: v.hours, pd: v.pd, count: v.count, employees: Array.from(v.employees).sort(), steps: Array.from(v.steps).sort() }};
  }}
  const byStepOut = {{}};
  for (const [k, v] of Object.entries(byStep)) {{
    byStepOut[k] = {{ hours: v.hours, pd: v.pd, count: v.count, employees: Array.from(v.employees).sort() }};
  }}

  return {{
    totalRecords,
    totalHours,
    totalPd,
    byEmployee: byEmployeeOut,
    byStory: byStoryOut,
    byStep: byStepOut,
    byDate,
    crossData,
    uniqueEmployees: Object.keys(byEmployee).length,
    uniqueStories: Object.keys(byStory).length,
  }};
}}

function filterRecords() {{
  const globalKw = document.getElementById("filter-global").value.trim().toLowerCase();
  const employee = document.getElementById("filter-employee").value;
  const step = document.getElementById("filter-step").value;
  const dateType = document.getElementById("filter-date-type").value;
  const dateValue = document.getElementById("filter-date-value").value;
  const storyKw = document.getElementById("filter-story").value.trim().toLowerCase();

  return ALL_RECORDS.filter(r => {{
    if (globalKw) {{
      const text = `${{r.employee || ""}} ${{r.step || ""}} ${{r.user_story || ""}} ${{r.remark || ""}}`.toLowerCase();
      if (!text.includes(globalKw)) return false;
    }}
    if (employee && r.employee !== employee) return false;
    if (step && r.step !== step) return false;
    if (storyKw) {{
      const story = (r.user_story || "").toLowerCase();
      if (!story.includes(storyKw)) return false;
    }}
    if (dateType && dateValue) {{
      if (dateType === "month" && r._yearMonth !== dateValue) return false;
      if (dateType === "quarter" && r._yearQuarter !== dateValue) return false;
      if (dateType === "year" && r._year !== dateValue) return false;
    }}
    return true;
  }});
}}

function updateDateValueOptions() {{
  const dateType = document.getElementById("filter-date-type").value;
  const dateValueSelect = document.getElementById("filter-date-value");
  dateValueSelect.innerHTML = "";
  if (!dateType) {{
    dateValueSelect.disabled = true;
    dateValueSelect.appendChild(new Option("请先选择日期维度", ""));
    return;
  }}

  const values = new Set();
  for (const r of ALL_RECORDS) {{
    if (dateType === "month" && r._yearMonth) values.add(r._yearMonth);
    if (dateType === "quarter" && r._yearQuarter) values.add(r._yearQuarter);
    if (dateType === "year" && r._year) values.add(r._year);
  }}

  dateValueSelect.disabled = false;
  dateValueSelect.appendChild(new Option(`全部${{dateType === "month" ? "月份" : dateType === "quarter" ? "季度" : "年度"}}`, ""));
  Array.from(values).sort().forEach(v => {{
    dateValueSelect.appendChild(new Option(v, v));
  }});
}}

function renderEmployee(stats) {{
  const tbody = document.getElementById("employee-tbody");
  if (Object.keys(stats.byEmployee).length === 0) {{ tbody.innerHTML = ""; return; }}
  const maxH = Math.max(...Object.values(stats.byEmployee).map(v => v.hours), 1);
  const emps = Object.keys(stats.byEmployee).sort((a, b) => stats.byEmployee[b].hours - stats.byEmployee[a].hours);
  tbody.innerHTML = emps.map(emp => {{
    const v = stats.byEmployee[emp];
    const w = maxH > 0 ? Math.round(v.hours / maxH * 100) : 0;
    return `<tr><td class="number">${{emp}}</td><td>${{v.pd.toFixed(1)}} 人天 (${{v.hours.toFixed(1)}} 小时)</td><td><span class="bar-container"><span class="bar green" style="width: ${{w}}%"></span></span></td><td>${{v.count}}</td><td>${{v.stories.length}}</td></tr>`;
  }}).join("");
}}

function renderStep(stats) {{
  const tbody = document.getElementById("step-tbody");
  if (Object.keys(stats.byStep).length === 0) {{ tbody.innerHTML = ""; return; }}
  const maxH = Math.max(...Object.values(stats.byStep).map(v => v.hours), 1);
  const steps = Object.keys(stats.byStep).sort((a, b) => stepSortKey(a) - stepSortKey(b));
  tbody.innerHTML = steps.map(step => {{
    const v = stats.byStep[step];
    const w = maxH > 0 ? Math.round(v.hours / maxH * 100) : 0;
    return `<tr><td class="number">${{step}}</td><td>${{v.pd.toFixed(1)}} 人天 (${{v.hours.toFixed(1)}} 小时)</td><td><span class="bar-container"><span class="bar blue" style="width: ${{w}}%"></span></span></td><td>${{v.count}}</td><td>${{v.employees.length}}</td></tr>`;
  }}).join("");
}}

function renderStory(stats) {{
  const tbody = document.getElementById("story-tbody");
  if (Object.keys(stats.byStory).length === 0) {{ tbody.innerHTML = ""; return; }}
  const maxH = Math.max(...Object.values(stats.byStory).map(v => v.hours), 1);
  const stories = Object.keys(stats.byStory).sort((a, b) => stats.byStory[b].hours - stats.byStory[a].hours);
  tbody.innerHTML = stories.map(story => {{
    const v = stats.byStory[story];
    const w = maxH > 0 ? Math.round(v.hours / maxH * 100) : 0;
    const empTags = v.employees.sort().map(e => `<span class="tag b">${{e}}</span>`).join(" ");
    const stepTags = v.steps.sort().map(s => `<span class="tag o">${{s}}</span>`).join(" ");
    return `<tr><td class="number">${{story}}</td><td>${{v.pd.toFixed(1)}} 人天 (${{v.hours.toFixed(1)}} 小时)</td><td><span class="bar-container"><span class="bar orange" style="width: ${{w}}%"></span></span></td><td>${{v.count}}</td><td>${{empTags}}</td><td>${{stepTags}}</td></tr>`;
  }}).join("");
}}

function renderDate(stats) {{
  const tbody = document.getElementById("date-tbody");
  if (Object.keys(stats.byDate).length === 0) {{ tbody.innerHTML = ""; return; }}
  const maxH = Math.max(...Object.values(stats.byDate).map(v => v.hours), 1);
  const dates = Object.keys(stats.byDate).sort();
  tbody.innerHTML = dates.map(date => {{
    const v = stats.byDate[date];
    const w = maxH > 0 ? Math.round(v.hours / maxH * 100) : 0;
    return `<tr><td class="number">${{date}}</td><td>${{v.pd.toFixed(1)}} 人天 (${{v.hours.toFixed(1)}} 小时)</td><td><span class="bar-container"><span class="bar purple" style="width: ${{w}}%"></span></span></td><td>${{v.count}}</td></tr>`;
  }}).join("");
}}

function renderCross(stats) {{
  const theadRow = document.querySelector(".cross-table thead tr");
  const tbody = document.getElementById("cross-tbody");
  const emps = Object.keys(stats.byEmployee).sort();
  const steps = Object.keys(stats.byStep).sort((a, b) => stepSortKey(a) - stepSortKey(b));

  // 表头
  let headHtml = "<th>员工</th>";
  for (const step of steps) headHtml += `<th>${{step}}</th>`;
  headHtml += "<th>合计</th>";
  theadRow.innerHTML = headHtml;

  if (emps.length === 0) {{ tbody.innerHTML = ""; return; }}
  tbody.innerHTML = emps.map(emp => {{
    const rowTotal = Object.values(stats.crossData[emp] || {{}}).reduce((a, b) => a + b, 0);
    let cells = steps.map(step => {{
      const val = (stats.crossData[emp] || {{}})[step] || 0;
      return val > 0 ? `<td>${{val.toFixed(1)}}</td>` : `<td>-</td>`;
    }}).join("");
    return `<tr><td class='number'>${{emp}}</td>${{cells}}<td class='number'>${{rowTotal.toFixed(1)}}</td></tr>`;
  }}).join("");
}}

function render(stats) {{
  document.getElementById("total-pd").innerHTML = `${{stats.totalPd.toFixed(1)}}<span class="unit">人天</span>`;
  document.getElementById("total-hours").innerHTML = `${{stats.totalHours.toFixed(1)}}<span class="unit">小时</span>`;
  document.getElementById("total-records").innerHTML = `${{stats.totalRecords}}<span class="unit">条</span>`;
  document.getElementById("total-unique").innerHTML = `${{stats.uniqueEmployees}}<span class="unit">人</span> / ${{stats.uniqueStories}}<span class="unit">个故事</span>`;

  if (stats.totalRecords === 0) {{
    document.getElementById("report-content").classList.add("hidden-section");
    document.getElementById("empty-tip").classList.remove("hidden-section");
    return;
  }}
  document.getElementById("report-content").classList.remove("hidden-section");
  document.getElementById("empty-tip").classList.add("hidden-section");

  renderEmployee(stats);
  renderStep(stats);
  renderStory(stats);
  renderDate(stats);
  renderCross(stats);
}}

function applyFilters() {{
  const filtered = filterRecords();
  const stats = computeStats(filtered);
  render(stats);

  const status = document.getElementById("filter-status");
  status.innerHTML = `当前共筛选出 <strong>${{filtered.length}}</strong> 条记录 / 全部 <strong>${{ALL_RECORDS.length}}</strong> 条`;
}}

function resetFilters() {{
  document.getElementById("filter-global").value = "";
  document.getElementById("filter-employee").value = "";
  document.getElementById("filter-step").value = "";
  document.getElementById("filter-date-type").value = "";
  document.getElementById("filter-story").value = "";
  updateDateValueOptions();
  applyFilters();
}}

// 监听日期维度变化，动态更新日期值选项
document.getElementById("filter-date-type").addEventListener("change", updateDateValueOptions);

// 监听回车键触发查询
document.querySelectorAll(".filter-item input").forEach(input => {{
  input.addEventListener("keypress", e => {{ if (e.key === "Enter") applyFilters(); }});
}});
</script>

</body>
</html>
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"HTML 分析报告已生成: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="生成时间节省分析报告 v2")
    parser.add_argument("--biz-line", default="", help="业务线（未指定时读取 config 中 default_biz_line）")
    parser.add_argument("--input", default="", help="外部 JSON 数据文件路径（云端同步数据），优先使用")
    parser.add_argument("--person", default="", help="个人报告模式：指定员工姓名，仅展示该员工的个人历史累计数据（跨所有用户故事、所有步骤）。不传则为全业务线报告。")
    parser.add_argument("--output", default="", help="输出文件路径（默认自动生成）")
    parser.add_argument("--format", choices=["html", "csv"], default="html", help="输出格式（默认：html）")

    args = parser.parse_args()

    from biz_line_helper import resolve_biz_line
    args.biz_line = resolve_biz_line(args.biz_line)

    records = load_records(args.biz_line, args.input if args.input else None)

    # 个人报告模式：预过滤为指定员工的所有记录
    person_name = args.person.strip() if args.person else ""
    if person_name:
        records = [r for r in records if r.get("employee", "").strip() == person_name]
        report_mode = "personal"
    else:
        report_mode = "admin"

    data_source = args.input if args.input else get_records_path(args.biz_line)

    # 确定输出文件名
    if not args.output:
        data_dir = get_data_dir(args.biz_line)
        if person_name:
            safe_name = person_name.replace(" ", "_")
            base = f"time_analytics_{args.biz_line}_{safe_name}"
        else:
            base = f"time_analytics_{args.biz_line}"
        args.output = os.path.join(data_dir, f"{base}.{'csv' if args.format == 'csv' else 'html'}")

    if not records:
        msg_person = f"员工 {person_name} 的" if person_name else f"{args.biz_line} 业务线的"
        print(f"暂无{msg_person}时间节省记录数据。")
        print(f"数据来源: {data_source}")
        if args.format == "csv":
            generate_csv(records, args.biz_line, args.output)
        else:
            generate_html(records, args.biz_line, args.output, person_name)
        return

    if args.format == "csv":
        generate_csv(records, args.biz_line, args.output)
    else:
        generate_html(records, args.biz_line, args.output, person_name)

    # 打印详细摘要
    total_hours = sum(r.get("total_hours", r.get("time_saved_hours", 0)) for r in records)
    total_pd = sum(r.get("time_saved_pd", 0) for r in records)
    unique_emps = set(r.get("employee", "") for r in records)
    unique_stories = set(r.get("user_story", "") for r in records)

    print(f"\n{'='*50}")
    print(f"📊 {args.biz_line}测试时间节省报告")
    print(f"   ({person_name} 个人视角)" if person_name else "   (业务线视角)")
    print(f"{'='*50}")
    print(f"   数据来源: {data_source}")
    print(f"   记录数: {len(records)} 条")
    print(f"   累计节省: {total_pd:.1f} 人天（{total_hours:.1f} 小时）")
    print(f"   参与员工: {len(unique_emps)} 人 ({', '.join(sorted(unique_emps))})")
    print(f"   覆盖故事: {len(unique_stories)} 个")

    # 按员工摘要
    by_emp = defaultdict(float)
    for r in records:
        by_emp[r.get("employee", "")] += r.get("total_hours", r.get("time_saved_hours", 0))
    print(f"\n   按员工分布:")
    for emp in sorted(by_emp.keys(), key=lambda e: by_emp[e], reverse=True):
        print(f"     {emp}: {by_emp[emp]/HOURS_PER_PD:.1f} 人天（{by_emp[emp]:.1f} 小时）")

    # 按步骤摘要（按固定顺序输出，兼容旧名称）
    def _step_sort_key(s):
        canonical = STEP_NAME_ALIASES.get(s, s)
        for code, name in STEP_NAMES.items():
            if name == canonical:
                return STEP_ORDER.index(code)
        return 99

    by_step_summary = defaultdict(float)
    for r in records:
        by_step_summary[r.get("step", "")] += r.get("total_hours", r.get("time_saved_hours", 0))
    print(f"\n   按步骤分布:")
    for step in sorted(by_step_summary.keys(), key=_step_sort_key):
        print(f"     {step}: {by_step_summary[step]/HOURS_PER_PD:.1f} 人天（{by_step_summary[step]:.1f} 小时）")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
